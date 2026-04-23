# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Per-bank ``.gitignore`` management.

The tool owns ``banks/<bank>/.gitignore``. Its job is one line:

  - Private bank: ``dist/\\n`` — keeps exported audio out of git.
  - Public bank: empty (or absent).

Anything else is "drifted": the file exists but doesn't match. Drift
shows up in the bank detail response so the UI can render a warning
banner. ``sync()`` rewrites the file atomically. All writes go through
temp-plus-``os.replace`` so a crash mid-write cannot leave a torn
file that accidentally exposes ``dist/``.

This module is a privacy-critical path (CLAUDE.md). Any change here
should ship with tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PRIVATE_CONTENT = "dist/\n"
PUBLIC_CONTENT = ""
_VALID_PRIVACY = ("public", "private")


@dataclass
class GitignoreStatus:
    status: str   # "ok" | "drifted" | "missing"
    expected: str
    current: str  # "" if the file is absent


class GitignoreSyncFailed(Exception):
    def __init__(self, message: str, *, bank_path: Path) -> None:
        self.message = message
        self.bank_path = bank_path
        super().__init__(message)


def expected_content(privacy: str) -> str:
    """Return the canonical ``.gitignore`` body for ``privacy``."""
    if privacy == "private":
        return PRIVATE_CONTENT
    if privacy == "public":
        return PUBLIC_CONTENT
    raise ValueError(f"privacy must be one of {_VALID_PRIVACY}, got {privacy!r}")


def verify(bank_path: Path, privacy: str) -> GitignoreStatus:
    """Compare the bank's current ``.gitignore`` against the expected body."""
    expected = expected_content(privacy)
    path = bank_path / ".gitignore"

    if not path.is_file():
        current = ""
        if privacy == "private":
            return GitignoreStatus("missing", expected, current)
        # Public + absent file = fine (root .gitignore handles raw/ + state.json).
        return GitignoreStatus("ok", expected, current)

    current = path.read_text(encoding="utf-8")
    if current == expected:
        return GitignoreStatus("ok", expected, current)
    return GitignoreStatus("drifted", expected, current)


def sync(bank_path: Path, privacy: str) -> GitignoreStatus:
    """Rewrite the bank's ``.gitignore`` so it matches ``privacy``.

    No-op in terms of disk I/O when already ``ok``; still returns the
    updated status. Atomic via temp-plus-``os.replace``.
    """
    status = verify(bank_path, privacy)
    if status.status == "ok":
        return status

    expected = status.expected
    path = bank_path / ".gitignore"
    tmp = path.with_name(".gitignore.tmp")

    try:
        tmp.write_text(expected, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        # Clean up the temp if it landed but replace failed; never leave
        # the bank in a partially-synced state.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        raise GitignoreSyncFailed(
            f"could not write {path}: {exc}",
            bank_path=bank_path,
        ) from exc

    return GitignoreStatus("ok", expected, expected)
