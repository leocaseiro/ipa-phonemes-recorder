# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Reference-audio resolution.

Order of attempts:
  1. references/<phoneme_id>.ogg  — CC-BY-SA audio cached locally by
     scripts/fetch_references.py
  2. espeak-ng synthesis via the static IPA→Kirshenbaum map
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ESPEAK_TIMEOUT_SECONDS = 10


@dataclass
class ReferenceResponse:
    body: bytes
    content_type: str
    source: str  # "wikimedia" or "espeak"
    attribution: str | None  # non-None iff source == "wikimedia"


class ReferenceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def load_ipa_espeak_map(seeds_dir: Path) -> dict[str, str]:
    """Return the IPA→Kirshenbaum map, or an empty dict if missing."""
    path = seeds_dir / "ipa_espeak_map.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Drop any keys starting with "_" (e.g. "_comment").
    return {k: v for k, v in raw.items() if isinstance(k, str) and not k.startswith("_")}


def serve_reference(
    *,
    phoneme: dict,
    references_root: Path,
    ipa_espeak_map: dict[str, str],
    espeak_binary: Path | None,
    attribution_path: Path,
) -> ReferenceResponse:
    phoneme_id = phoneme.get("id", "")

    ogg_path = references_root / f"{phoneme_id}.ogg"
    if ogg_path.is_file():
        return ReferenceResponse(
            body=ogg_path.read_bytes(),
            content_type="audio/ogg",
            source="wikimedia",
            attribution=read_attribution(attribution_path, phoneme_id),
        )

    return _espeak_fallback(phoneme, ipa_espeak_map, espeak_binary)


def _espeak_fallback(
    phoneme: dict,
    ipa_espeak_map: dict[str, str],
    espeak_binary: Path | None,
) -> ReferenceResponse:
    ipa = phoneme.get("ipa", "")
    kirshenbaum = ipa_espeak_map.get(ipa)
    if not kirshenbaum:
        raise ReferenceError(
            "espeak_no_mapping",
            f"no espeak-ng mapping for IPA {ipa!r} — add an entry to server/seeds/ipa_espeak_map.json",
        )
    if espeak_binary is None:
        raise ReferenceError(
            "espeak_unavailable",
            "espeak-ng not on PATH; install with: brew install espeak-ng",
        )
    try:
        result = subprocess.run(
            [
                str(espeak_binary),
                "-v", "en",
                "-s", "120",
                "--stdout",
                f"[[{kirshenbaum}]]",
            ],
            capture_output=True,
            timeout=ESPEAK_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ReferenceError(
            "espeak_failed",
            f"espeak-ng timed out after {ESPEAK_TIMEOUT_SECONDS}s",
        ) from exc

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")[:300]
        raise ReferenceError(
            "espeak_failed",
            f"espeak-ng exited {result.returncode}: {stderr}",
        )

    return ReferenceResponse(
        body=result.stdout,
        content_type="audio/wav",
        source="espeak",
        attribution=None,
    )


def read_attribution(attribution_path: Path, phoneme_id: str) -> str | None:
    """Parse one attribution line out of ATTRIBUTION.md.

    Lines written by fetch_references.py follow the format:
        - <phoneme_id>: <uploader> / <licence> / <commons_page>
    Anything else is ignored.
    """
    if not attribution_path.is_file():
        return None
    prefix = f"- {phoneme_id}: "
    try:
        for line in attribution_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(prefix):
                return line[len(prefix):].strip()
    except OSError as exc:
        logger.warning("failed to read %s: %s", attribution_path, exc)
    return None
