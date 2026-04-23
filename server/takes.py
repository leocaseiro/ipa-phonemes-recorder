# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Take recording: transcode upload, compute metadata, update state.

Take IDs are monotonic within a phoneme and never reused — the next
id is `max(state_ids ∪ disk_ids) + 1`, zero-padded to three digits.
This preserves a stable history even when takes are deleted.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from server.audio_meta import compute_peak_rms
from server.state import read_state, write_state

logger = logging.getLogger(__name__)

TAKE_ID_RE = re.compile(r"^take-(\d+)$")
FFMPEG_TIMEOUT_SECONDS = 30


@dataclass
class TakeMeta:
    take_id: str
    duration_ms: int
    peak_db: float
    rms_db: float
    created_at: str


class TakeSaveFailed(Exception):
    def __init__(self, code: str, message: str, detail: str = "", tmp_path: Path | None = None):
        self.code = code
        self.message = message
        self.detail = detail
        self.tmp_path = tmp_path
        super().__init__(f"{code}: {message}")


class TakeNotFound(Exception):
    def __init__(self, phoneme_id: str, take_id: str):
        self.phoneme_id = phoneme_id
        self.take_id = take_id
        super().__init__(f"take not found: {phoneme_id}/{take_id}")


def next_take_id(phoneme_dir: Path, state: dict, phoneme_id: str) -> str:
    max_n = 0
    phoneme_state = state.get("phonemes", {}).get(phoneme_id, {})
    for take in phoneme_state.get("takes", []):
        m = TAKE_ID_RE.match(take.get("id", ""))
        if m:
            max_n = max(max_n, int(m.group(1)))
    if phoneme_dir.is_dir():
        for wav in phoneme_dir.iterdir():
            if wav.suffix != ".wav":
                continue
            m = TAKE_ID_RE.match(wav.stem)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return f"take-{max_n + 1:03d}"


def save_take(
    *,
    bank_path: Path,
    phoneme_id: str,
    src_bytes: bytes,
    src_ext: str,
    ffmpeg: Path,
    tmp_root: Path,
) -> TakeMeta:
    phoneme_dir = bank_path / "raw" / phoneme_id
    state = read_state(bank_path)
    take_id = next_take_id(phoneme_dir, state, phoneme_id)

    tmp_dir = tmp_root / bank_path.name / phoneme_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_src = tmp_dir / f"{take_id}{src_ext}"
    tmp_src.write_bytes(src_bytes)

    phoneme_dir.mkdir(parents=True, exist_ok=True)
    wav_path = phoneme_dir / f"{take_id}.wav"

    try:
        result = subprocess.run(
            [
                str(ffmpeg), "-y", "-i", str(tmp_src),
                "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise TakeSaveFailed(
            "ffmpeg_timeout",
            f"ffmpeg timed out after {FFMPEG_TIMEOUT_SECONDS}s",
            tmp_path=tmp_src,
        ) from exc

    if result.returncode != 0:
        if wav_path.exists():
            wav_path.unlink()
        raise TakeSaveFailed(
            "ffmpeg_failed",
            "transcoding failed",
            detail=result.stderr[-1500:],
            tmp_path=tmp_src,
        )

    try:
        peak_db, rms_db, duration_ms = compute_peak_rms(wav_path)
    except Exception as exc:
        wav_path.unlink(missing_ok=True)
        raise TakeSaveFailed(
            "wav_unreadable",
            "transcoded WAV could not be measured",
            detail=str(exc),
            tmp_path=tmp_src,
        ) from exc

    created_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    phonemes = state.setdefault("phonemes", {})
    if phoneme_id not in phonemes:
        phonemes[phoneme_id] = {"keeper_take": None, "takes": []}
    phoneme_entry = phonemes[phoneme_id]
    phoneme_entry.setdefault("keeper_take", None)
    phoneme_entry.setdefault("takes", [])
    phoneme_entry["takes"].append(
        {
            "id": take_id,
            "created_at": created_at,
            "duration_ms": duration_ms,
            "peak_db": peak_db,
            "rms_db": rms_db,
            "notes": "",
        }
    )
    state["last_phoneme_id"] = phoneme_id
    write_state(bank_path, state)

    try:
        tmp_src.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("could not clean up %s: %s", tmp_src, exc)

    return TakeMeta(
        take_id=take_id,
        duration_ms=duration_ms,
        peak_db=peak_db,
        rms_db=rms_db,
        created_at=created_at,
    )


def get_take_wav_path(bank_path: Path, phoneme_id: str, take_id: str) -> Path:
    if not TAKE_ID_RE.match(take_id):
        raise TakeNotFound(phoneme_id, take_id)
    wav = bank_path / "raw" / phoneme_id / f"{take_id}.wav"
    if not wav.is_file():
        raise TakeNotFound(phoneme_id, take_id)
    return wav


def delete_take(*, bank_path: Path, phoneme_id: str, take_id: str) -> dict:
    """Remove the take's WAV + state entry. Returns the updated state.

    Siblings are not renumbered — take IDs are monotonic forever. If
    the take was the keeper, clears keeper_take on that phoneme.
    Raises TakeNotFound if neither the state entry nor the WAV exists.
    """
    if not TAKE_ID_RE.match(take_id):
        raise TakeNotFound(phoneme_id, take_id)

    state = read_state(bank_path)
    phoneme = state.get("phonemes", {}).get(phoneme_id, {})
    takes = phoneme.get("takes", []) if isinstance(phoneme, dict) else []
    wav_path = bank_path / "raw" / phoneme_id / f"{take_id}.wav"

    has_state_entry = any(
        isinstance(t, dict) and t.get("id") == take_id for t in takes
    )
    has_disk = wav_path.is_file()
    if not has_state_entry and not has_disk:
        raise TakeNotFound(phoneme_id, take_id)

    if isinstance(phoneme, dict):
        phoneme["takes"] = [
            t for t in takes if not (isinstance(t, dict) and t.get("id") == take_id)
        ]
        if phoneme.get("keeper_take") == take_id:
            phoneme["keeper_take"] = None
    write_state(bank_path, state)

    if has_disk:
        try:
            wav_path.unlink()
        except OSError as exc:
            logger.warning("failed to remove %s: %s", wav_path, exc)

    return state
