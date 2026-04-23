# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""BaseSkill-compatible bank export.

Pipeline (spec §12 / plan §13.3):
  1. Collect keeper WAVs from config + state.
  2. Per keeper, ffmpeg silenceremove + loudnorm + 22.05 kHz mono.
  3. Generate one 25 ms silence WAV; interleave with phonemes.
  4. Probe each per-phoneme intermediate WAV for duration (ffprobe);
     compute cumulative manifest offsets in Python so they stay
     deterministic even if the MP3 encoder adds frame padding.
  5. ffmpeg concat demuxer → libmp3lame (VBR ~56 kbps, 22.05 kHz mono).
  6. Atomic write onto dist/phonemes.{mp3,json}.

`references/` is never opened here — the pipeline works from
``bank_path / "raw" / <phoneme_id> / <take>.wav`` only. Confirmed by
code review (spec §11.3). No runtime assertion in v1.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from server.ffmpeg_util import FfmpegError, probe_duration_ms, run

SILENCE_GAP_MS = 25
TARGET_SAMPLE_RATE = 22050
DEFAULT_TARGET_LUFS = -16


@dataclass
class ExportSummary:
    phoneme_count: int
    exported_count: int
    skipped: list[dict]
    duration_ms: int
    mp3_bytes: int
    manifest_bytes: int
    warnings: list[str] = field(default_factory=list)


class ExportError(Exception):
    def __init__(self, code: str, message: str, detail: str = "", **extra) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        self.extra = extra
        super().__init__(f"{code}: {message}")


def export_bank(
    *,
    bank_path: Path,
    config: dict,
    state: dict,
    ffmpeg: Path,
    tmp_root: Path,
    ffprobe: Path | None = None,
    on_missing_keeper: str = "skip",
    deterministic: bool = False,
) -> ExportSummary:
    """Build dist/phonemes.{mp3,json} from the bank's keeper takes."""
    if on_missing_keeper not in ("skip", "fail"):
        raise ExportError(
            "bad_request",
            f"on_missing_keeper must be 'skip' or 'fail', got {on_missing_keeper!r}",
        )

    target_lufs = config.get("target_lufs", DEFAULT_TARGET_LUFS)
    phonemes = config.get("phonemes", [])

    keepers, skipped = _collect_keepers(bank_path, phonemes, state)

    if on_missing_keeper == "fail" and skipped:
        raise ExportError(
            "missing_keepers",
            f"{len(skipped)} phoneme(s) without a keeper take",
            detail=json.dumps(skipped, ensure_ascii=False),
            skipped=skipped,
        )

    if not keepers:
        raise ExportError(
            "zero_keepers",
            "bank has no keeper takes to export — record + keeper at least one phoneme first",
        )

    bank_tmp = tmp_root / bank_path.name
    if bank_tmp.exists():
        shutil.rmtree(bank_tmp, ignore_errors=True)
    bank_tmp.mkdir(parents=True, exist_ok=True)

    try:
        filtered = _filter_keepers(
            ffmpeg=ffmpeg,
            keepers=keepers,
            tmp_dir=bank_tmp,
            target_lufs=target_lufs,
            deterministic=deterministic,
        )
        silence_wav = bank_tmp / "_silence.wav"
        _make_silence(ffmpeg, silence_wav, SILENCE_GAP_MS)

        manifest, total_ms = _build_manifest(filtered, silence_wav, ffprobe=ffprobe)
        concat_list = _write_concat_list(bank_tmp, filtered, silence_wav)

        tmp_mp3 = bank_tmp / "phonemes.mp3"
        _concat_encode_mp3(ffmpeg, concat_list, tmp_mp3)

        tmp_manifest = bank_tmp / "phonemes.json"
        tmp_manifest.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        dist_dir = bank_path / "dist"
        dist_dir.mkdir(exist_ok=True)
        final_mp3 = dist_dir / "phonemes.mp3"
        final_manifest = dist_dir / "phonemes.json"
        os.replace(tmp_mp3, final_mp3)
        os.replace(tmp_manifest, final_manifest)

        summary = ExportSummary(
            phoneme_count=len(phonemes),
            exported_count=len(filtered),
            skipped=skipped if on_missing_keeper == "skip" else [],
            duration_ms=total_ms,
            mp3_bytes=final_mp3.stat().st_size,
            manifest_bytes=final_manifest.stat().st_size,
        )
    except (FfmpegError, ExportError):
        # Preserve bank_tmp for debugging; the next successful run wipes it.
        raise
    else:
        shutil.rmtree(bank_tmp, ignore_errors=True)
        return summary


def _collect_keepers(
    bank_path: Path, phonemes: list[dict], state: dict
) -> tuple[list[tuple[dict, Path]], list[dict]]:
    keepers: list[tuple[dict, Path]] = []
    skipped: list[dict] = []
    phonemes_state = state.get("phonemes", {}) if isinstance(state, dict) else {}

    for phoneme in phonemes:
        pid = phoneme.get("id")
        if not isinstance(pid, str):
            continue
        ph_state = phonemes_state.get(pid) or {}
        keeper_id = ph_state.get("keeper_take") if isinstance(ph_state, dict) else None
        if not keeper_id:
            skipped.append(
                {
                    "id": pid,
                    "ipa": phoneme.get("ipa", ""),
                    "reason": "no keeper",
                }
            )
            continue
        wav = bank_path / "raw" / pid / f"{keeper_id}.wav"
        if not wav.is_file():
            skipped.append(
                {
                    "id": pid,
                    "ipa": phoneme.get("ipa", ""),
                    "reason": f"keeper WAV missing on disk: {wav.name}",
                }
            )
            continue
        keepers.append((phoneme, wav))
    return keepers, skipped


def _filter_keepers(
    *,
    ffmpeg: Path,
    keepers: list[tuple[dict, Path]],
    tmp_dir: Path,
    target_lufs: int | float,
    deterministic: bool,
) -> list[tuple[dict, Path]]:
    out: list[tuple[dict, Path]] = []
    for phoneme, wav in keepers:
        dest = tmp_dir / f"{phoneme['id']}.wav"
        filters = ["silenceremove=stop_periods=-1:stop_duration=0.05:stop_threshold=-50dB"]
        if not deterministic:
            filters.append(f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11")
        cmd = [
            str(ffmpeg),
            "-y",
            "-i", str(wav),
            "-af", ",".join(filters),
            "-ar", str(TARGET_SAMPLE_RATE),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(dest),
        ]
        run(cmd)
        out.append((phoneme, dest))
    return out


def _make_silence(ffmpeg: Path, dest: Path, ms: int) -> None:
    cmd = [
        str(ffmpeg),
        "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={TARGET_SAMPLE_RATE}:cl=mono",
        "-t", f"{ms / 1000:.3f}",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(dest),
    ]
    run(cmd)


def _build_manifest(
    filtered: list[tuple[dict, Path]],
    silence_wav: Path,
    *,
    ffprobe: Path | None,
) -> tuple[dict, int]:
    silence_ms = probe_duration_ms(silence_wav, ffprobe=ffprobe)
    manifest: dict = {}
    cumulative = 0
    for idx, (phoneme, wav) in enumerate(filtered):
        dur = probe_duration_ms(wav, ffprobe=ffprobe)
        entry: dict = {"start": cumulative, "duration": dur}
        if phoneme.get("loopable"):
            entry["loopable"] = True
        manifest[phoneme["ipa"]] = entry
        cumulative += dur
        if idx < len(filtered) - 1:
            cumulative += silence_ms
    return manifest, cumulative


def _write_concat_list(
    tmp_dir: Path,
    filtered: list[tuple[dict, Path]],
    silence_wav: Path,
) -> Path:
    concat = tmp_dir / "concat.txt"
    lines: list[str] = []
    for idx, (_phoneme, wav) in enumerate(filtered):
        lines.append(f"file '{wav.name}'")
        if idx < len(filtered) - 1:
            lines.append(f"file '{silence_wav.name}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return concat


def _concat_encode_mp3(ffmpeg: Path, concat_list: Path, dest: Path) -> None:
    cmd = [
        str(ffmpeg),
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:a", "libmp3lame",
        "-q:a", "6",
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", "1",
        str(dest),
    ]
    run(cmd)
