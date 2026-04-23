# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Reference-audio resolution.

Two bundled corpora (local files only, no TTS):

- **PolyU** — Hong Kong PolyU ELC (
  `references/polyu/*.mp3`, map `server/seeds/phoneme_polyu_files.json`
  from https://elc.polyu.edu.hk/sounds/ — run
  `python3 scripts/fetch_polyu_references.py`).

- **Vocabulary.com** — `server/seeds/phoneme_reference_files.json`, files
  under `references/`.

`GET` supports `?source=auto` (default: PolyU if present, else
Vocabulary), `polyu`, or `vocabulary`.

The `references/` tree is gitignored. Audio may be licence-restricted;
it stays on the user machine and is read-only in export (spec §11.3).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_REFERENCE_EXTENSIONS = (
    ("ogg", "audio/ogg"),
    ("mp3", "audio/mpeg"),
)


@dataclass
class ReferenceResponse:
    body: bytes
    content_type: str
    source: str
    attribution: str | None


class ReferenceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def load_ipa_espeak_map(seeds_dir: Path) -> dict[str, str]:
    """Legacy IPA map (not used for HTTP reference preview)."""
    path = seeds_dir / "ipa_espeak_map.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if isinstance(k, str) and not k.startswith("_")}


def load_phoneme_reference_files(seeds_dir: Path) -> dict[str, str]:
    path = seeds_dir / "phoneme_reference_files.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        k: v
        for k, v in raw.items()
        if isinstance(k, str) and not k.startswith("_") and isinstance(v, str) and v
    }


def load_phoneme_polyu_files(seeds_dir: Path) -> dict[str, str]:
    path = seeds_dir / "phoneme_polyu_files.json"
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        k: v
        for k, v in raw.items()
        if isinstance(k, str) and not k.startswith("_") and isinstance(v, str) and v
    }


def serve_reference(
    *,
    phoneme: dict,
    references_root: Path,
    phoneme_polyu_files: dict[str, str],
    phoneme_reference_files: dict[str, str],
    source: str,
    attribution_path: Path,
) -> ReferenceResponse:
    """Resolve one reference clip. ``source`` is auto | polyu | vocabulary."""
    mode = (source or "auto").strip().lower()
    if mode not in ("auto", "polyu", "vocabulary"):
        mode = "auto"

    phoneme_id = phoneme.get("id", "")
    ipa = phoneme.get("ipa", "")

    if mode == "vocabulary":
        r = _try_vocabulary(
            references_root, phoneme_id, phoneme_reference_files, attribution_path
        )
        if r is not None:
            return r
        raise ReferenceError(
            "reference_missing",
            f"no Vocabulary.com–mapped file for {phoneme_id!r} (IPA {ipa!r}) under {references_root}.",
        )

    if mode == "polyu":
        r = _try_polyu(references_root, phoneme_id, phoneme_polyu_files)
        if r is not None:
            return r
        raise ReferenceError(
            "reference_missing",
            (
                f"no PolyU clip for {phoneme_id!r} (IPA {ipa!r}). "
                f"Run: python3 scripts/fetch_polyu_references.py "
                f"— files go under {references_root / 'polyu'}."
            ),
        )

    # auto: PolyU first, then Vocabulary
    r = _try_polyu(references_root, phoneme_id, phoneme_polyu_files)
    if r is not None:
        return r
    r = _try_vocabulary(
        references_root, phoneme_id, phoneme_reference_files, attribution_path
    )
    if r is not None:
        return r
    raise ReferenceError(
        "reference_missing",
        (
            f"no reference audio for {phoneme_id!r} (IPA {ipa!r}). "
            f"Try: python3 scripts/fetch_polyu_references.py "
            f"and/or Vocabulary.com files per server/seeds/phoneme_reference_files.json."
        ),
    )


def _try_polyu(
    references_root: Path, phoneme_id: str, polyu: dict[str, str]
) -> ReferenceResponse | None:
    name = polyu.get(phoneme_id)
    if not name:
        return None
    path = references_root / "polyu" / name
    if not path.is_file():
        return None
    ext = path.suffix.lower().lstrip(".")
    content_type = {
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
    }.get(ext, "application/octet-stream")
    return ReferenceResponse(
        body=path.read_bytes(),
        content_type=content_type,
        source="polyu",
        attribution=None,
    )


def _try_vocabulary(
    references_root: Path,
    phoneme_id: str,
    phoneme_reference_files: dict[str, str],
    attribution_path: Path,
) -> ReferenceResponse | None:
    alt = phoneme_reference_files.get(phoneme_id)
    if alt:
        path = references_root / alt
        if path.is_file():
            ext = path.suffix.lower().lstrip(".")
            content_type = {
                "mp3": "audio/mpeg",
                "ogg": "audio/ogg",
            }.get(ext, "application/octet-stream")
            return ReferenceResponse(
                body=path.read_bytes(),
                content_type=content_type,
                source="vocabulary",
                attribution=None,
            )

    for ext, content_type in LOCAL_REFERENCE_EXTENSIONS:
        path = references_root / f"{phoneme_id}.{ext}"
        if path.is_file():
            wikimedia = ext == "ogg"
            return ReferenceResponse(
                body=path.read_bytes(),
                content_type=content_type,
                source="wikimedia" if wikimedia else "file",
                attribution=(
                    read_attribution(attribution_path, phoneme_id) if wikimedia else None
                ),
            )
    return None


def read_attribution(attribution_path: Path, phoneme_id: str) -> str | None:
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


# Catalog for the UI and OpenAPI–style clients.
REFERENCE_SOURCES: tuple[tuple[str, str], ...] = (
    (
        "auto",
        "Auto — PolyU ELC (HK) if downloaded, else Vocabulary.com",
    ),
    (
        "polyu",
        "PolyU ELC (https://elc.polyu.edu.hk/sounds/)",
    ),
    (
        "vocabulary",
        "Vocabulary.com (see server/seeds/phoneme_reference_files.json)",
    ),
)
