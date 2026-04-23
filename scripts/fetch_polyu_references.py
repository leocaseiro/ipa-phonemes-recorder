#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Download PolyU ELC /pron/ipa/*.mp3 into references/polyu/.

Fetches the official lesson pages under https://elc.polyu.edu.hk/sounds/,
collects all pron/ipa/ links, and downloads each (idempotent: skips
existing). Intended for private local reference only — mirror academic
ELT material in line with the host site and your use case.

Run:
    python3 scripts/fetch_polyu_references.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

if sys.version_info < (3, 10):
    sys.exit("This script requires Python 3.10+")

BASE = "https://elc.polyu.edu.hk/sounds"
USER_AGENT = (
    "ipa-phonemes-recorder/0.1 (local script; https://elc.polyu.edu.hk ELC material)"
)
TIMEOUT = 30
MP3_IN_HTML = re.compile(r"pron/ipa/[^\"'<> ]+\.mp3", re.I)


def discover_urls() -> set[str]:
    index = _fetch(f"{BASE}/index.htm")
    htm = set(re.findall(r"lesson[0-9-]+\.htm", index, re.I))
    mp3: set[str] = set()
    for rel in sorted(htm):
        try:
            body = _fetch(f"{BASE}/{rel}")
        except urllib.error.URLError as exc:
            print(f"skip   {rel} — {exc}", file=sys.stderr)
            continue
        for m in MP3_IN_HTML.finditer(body):
            mp3.add(f"{BASE}/{m.group(0)}")
    return mp3


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "references" / "polyu"
    out_dir.mkdir(parents=True, exist_ok=True)

    urls = discover_urls()
    if not urls:
        print("No pron/ipa/*.mp3 links found — the site may have changed.", file=sys.stderr)
        return 1

    seed = root / "server" / "seeds" / "phoneme_polyu_files.json"
    ok = 0
    skip = 0
    fail = 0
    for u in sorted(urls):
        name = u.rsplit("/", 1)[-1]
        target = out_dir / name
        if target.is_file() and target.stat().st_size > 0:
            print(f"skip   {name}")
            skip += 1
            continue
        try:
            _download(u, target)
        except (urllib.error.URLError, OSError) as exc:
            print(f"FAIL   {name} — {exc}", file=sys.stderr)
            fail += 1
            continue
        print(f"ok     {name}")
        ok += 1

    print()
    print(f"downloaded {ok}, skipped {skip}, failed {fail}, total discovered {len(urls)}")

    if seed.is_file():
        j = json.loads(seed.read_text(encoding="utf-8"))
        need = {v for k, v in j.items() if not k.startswith("_") and isinstance(v, str)}
        for name in sorted(need - {p.name for p in out_dir.glob("*.mp3")}):
            url = f"{BASE}/pron/ipa/{name}"
            target = out_dir / name
            if target.is_file() and target.stat().st_size > 0:
                continue
            try:
                _download(url, target)
                print(f"ok     (direct) {name}")
            except (urllib.error.URLError, OSError) as exc:
                print(f"FAIL   (direct) {name} — {exc}", file=sys.stderr)
                fail += 1

        have = {p.name for p in out_dir.glob("*.mp3")}
        miss2 = need - have
        if miss2:
            print("warning: phoneme_polyu_files.json still missing on disk:", file=sys.stderr)
            for m in sorted(miss2):
                print(f"  {m}", file=sys.stderr)
    return 0 if fail == 0 else 1


def _download(url: str, target: Path) -> None:
    tmp = target.with_suffix(target.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310
        tmp.write_bytes(resp.read())
    tmp.replace(target)


if __name__ == "__main__":
    raise SystemExit(main())
