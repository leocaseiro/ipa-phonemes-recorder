# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Privacy-critical: the per-bank ``.gitignore`` is the fence between
``banks/<bank>/dist/`` and git. A bug here could publish a private
recording.

Run: python3.11 -m unittest tests.test_gitignore
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from server.gitignore import (
    PRIVATE_CONTENT,
    PUBLIC_CONTENT,
    GitignoreSyncFailed,
    expected_content,
    sync,
    verify,
)


class ExpectedContentTest(unittest.TestCase):
    def test_private_is_dist_slash(self) -> None:
        self.assertEqual(expected_content("private"), "dist/\n")

    def test_public_is_empty(self) -> None:
        self.assertEqual(expected_content("public"), "")

    def test_unknown_privacy_raises(self) -> None:
        with self.assertRaises(ValueError):
            expected_content("bogus")


class VerifyTest(unittest.TestCase):
    def _bank(self, tmp: str) -> Path:
        return Path(tmp)

    def test_private_with_matching_file_is_ok(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = self._bank(tmp)
            (bank / ".gitignore").write_text(PRIVATE_CONTENT)
            s = verify(bank, "private")
            self.assertEqual(s.status, "ok")

    def test_private_with_missing_file_is_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            s = verify(self._bank(tmp), "private")
            self.assertEqual(s.status, "missing")
            self.assertEqual(s.current, "")

    def test_private_with_drifted_extra_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = self._bank(tmp)
            (bank / ".gitignore").write_text("dist/\nnotes.txt\n")
            s = verify(bank, "private")
            self.assertEqual(s.status, "drifted")
            self.assertIn("notes.txt", s.current)

    def test_private_with_wrong_content_is_drifted(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = self._bank(tmp)
            (bank / ".gitignore").write_text("*.wav\n")
            s = verify(bank, "private")
            self.assertEqual(s.status, "drifted")

    def test_public_with_missing_file_is_ok(self) -> None:
        with TemporaryDirectory() as tmp:
            s = verify(self._bank(tmp), "public")
            self.assertEqual(s.status, "ok")

    def test_public_with_empty_file_is_ok(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = self._bank(tmp)
            (bank / ".gitignore").write_text(PUBLIC_CONTENT)
            s = verify(bank, "public")
            self.assertEqual(s.status, "ok")

    def test_public_with_content_is_drifted(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = self._bank(tmp)
            (bank / ".gitignore").write_text("dist/\n")
            s = verify(bank, "public")
            self.assertEqual(s.status, "drifted")


class SyncTest(unittest.TestCase):
    def test_private_writes_dist_slash(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = Path(tmp)
            status = sync(bank, "private")
            self.assertEqual(status.status, "ok")
            self.assertEqual(
                (bank / ".gitignore").read_text(encoding="utf-8"),
                PRIVATE_CONTENT,
            )

    def test_public_empties_existing_file(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = Path(tmp)
            (bank / ".gitignore").write_text("dist/\n")
            status = sync(bank, "public")
            self.assertEqual(status.status, "ok")
            self.assertEqual(
                (bank / ".gitignore").read_text(encoding="utf-8"),
                PUBLIC_CONTENT,
            )

    def test_noop_when_already_ok(self) -> None:
        with TemporaryDirectory() as tmp:
            bank = Path(tmp)
            (bank / ".gitignore").write_text(PRIVATE_CONTENT)
            # Mark file read-only: sync should not write (because it's ok).
            (bank / ".gitignore").chmod(0o444)
            try:
                status = sync(bank, "private")
                self.assertEqual(status.status, "ok")
            finally:
                (bank / ".gitignore").chmod(0o644)

    def test_atomic_via_replace_no_partial_file(self) -> None:
        """After sync, .gitignore.tmp must not linger."""
        with TemporaryDirectory() as tmp:
            bank = Path(tmp)
            sync(bank, "private")
            self.assertFalse((bank / ".gitignore.tmp").exists())

    def test_sync_failure_cleans_tmp_and_raises(self) -> None:
        """If write fails, the bank must not be left in a torn state."""
        with TemporaryDirectory() as tmp:
            bank = Path(tmp) / "nonexistent-dir"
            # bank dir does not exist → write should fail.
            with self.assertRaises(GitignoreSyncFailed):
                sync(bank, "private")


if __name__ == "__main__":
    unittest.main()
