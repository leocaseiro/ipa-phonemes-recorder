#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""One-shot Wikimedia IPA-audio downloader.

Populates `references/<phoneme_id>.ogg` from a hand-curated table of
Commons URLs and records credit/licence lines in
`references/ATTRIBUTION.md`. Idempotent: present files are skipped,
attribution lines already present are not re-appended.

Expansion: browse
    https://en.wikipedia.org/wiki/IPA_consonant_chart_with_audio
    https://en.wikipedia.org/wiki/IPA_vowel_chart_with_audio
pick the OGG URL for each phoneme from the media viewer, and record
the uploader + licence from the Commons file page. Append a
ReferenceEntry(...) row to WIKIMEDIA_REFERENCES below.

Run:
    python3.11 scripts/fetch_references.py
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

if sys.version_info < (3, 10):
    sys.stderr.write(
        f"ipa-phonemes-recorder requires Python 3.10+, got {sys.version.split()[0]}. "
        f"Try: python3.11 scripts/fetch_references.py\n"
    )
    raise SystemExit(1)

USER_AGENT = (
    "ipa-phonemes-recorder/0.1 "
    "(https://github.com/leocaseiro/ipa-phonemes-recorder; local tool)"
)
DOWNLOAD_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class ReferenceEntry:
    phoneme_id: str     # matches config.json.phonemes[].id
    ipa: str            # sanity record; not used at download time
    url: str            # direct link to the .ogg on upload.wikimedia.org
    licence: str        # e.g. "CC BY-SA 3.0"
    uploader: str       # Commons username
    commons_page: str   # https://commons.wikimedia.org/wiki/File:...


# The table starts empty on purpose. The tool runs fine without it
# (the server falls back to espeak-ng synthesis); curating URLs is a
# gradual job. Add entries as needed.
WIKIMEDIA_REFERENCES: list[ReferenceEntry] = [
    # ReferenceEntry(
    #     phoneme_id="sh",
    #     ipa="ʃ",
    #     url="https://upload.wikimedia.org/.../Voiceless_postalveolar_fricative.ogg",
    #     licence="CC BY-SA 3.0",
    #     uploader="Peter238",
    #     commons_page="https://commons.wikimedia.org/wiki/File:Voiceless_postalveolar_fricative.ogg",
    # ),
]


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    refs_dir = repo_root / "references"
    refs_dir.mkdir(exist_ok=True)
    attribution_path = refs_dir / "ATTRIBUTION.md"
    ensure_attribution_header(attribution_path)

    if not WIKIMEDIA_REFERENCES:
        print(
            "WIKIMEDIA_REFERENCES is empty — nothing to fetch. "
            "The recorder will fall back to espeak-ng synthesis. "
            "Edit scripts/fetch_references.py to add entries."
        )
        return 0

    downloaded = 0
    skipped = 0
    failed = 0

    for entry in WIKIMEDIA_REFERENCES:
        target = refs_dir / f"{entry.phoneme_id}.ogg"
        if target.is_file():
            print(f"skip   {entry.phoneme_id:<8} (already present)")
            skipped += 1
            continue
        if _download(entry.url, target):
            _append_attribution_row(attribution_path, entry)
            print(f"ok     {entry.phoneme_id:<8} {entry.url}")
            downloaded += 1
        else:
            failed += 1

    print()
    print(f"downloaded {downloaded}, skipped {skipped}, failed {failed}")
    return 0 if failed == 0 else 1


def _download(url: str, target: Path) -> bool:
    tmp = target.with_name(target.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
            tmp.write_bytes(resp.read())
    except urllib.error.URLError as exc:
        print(f"FAIL   {url} — {exc}")
        tmp.unlink(missing_ok=True)
        return False
    except TimeoutError:
        print(f"FAIL   {url} — timeout after {DOWNLOAD_TIMEOUT_SECONDS}s")
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(target)
    return True


def ensure_attribution_header(attribution_path: Path) -> None:
    if attribution_path.is_file():
        return
    attribution_path.write_text(
        "# Reference audio attribution\n"
        "\n"
        "Source files cached from Wikimedia Commons. Each entry below\n"
        "records the uploader and licence for the OGG stored at\n"
        "`references/<phoneme_id>.ogg`. Format:\n"
        "\n"
        "    - <phoneme_id>: <uploader> / <licence> / <commons_page>\n"
        "\n",
        encoding="utf-8",
    )


def _append_attribution_row(attribution_path: Path, entry: ReferenceEntry) -> None:
    row = (
        f"- {entry.phoneme_id}: {entry.uploader} / {entry.licence} "
        f"/ {entry.commons_page}\n"
    )
    current = attribution_path.read_text(encoding="utf-8")
    if row in current:
        return
    if not current.endswith("\n"):
        current += "\n"
    attribution_path.write_text(current + row, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
