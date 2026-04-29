# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Regression tests for the monotonic take-numbering rule.

Per spec §6.3 / plan §10.3 step 4: deletes never decrement the
counter. After any take-NNN has existed, its number can never be
reused — even if the take is the highest and only one on disk.

Run: python3.11 -m unittest tests.test_takes
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from server.takes import next_take_id


class MonotonicTakeIdTest(unittest.TestCase):
    def test_starts_at_001_when_empty(self) -> None:
        with TemporaryDirectory() as tmp:
            phoneme_dir = Path(tmp)
            state: dict = {"phonemes": {}}
            self.assertEqual(next_take_id(phoneme_dir, state, "sh"), "take-001")

    def test_picks_max_plus_one_from_disk(self) -> None:
        with TemporaryDirectory() as tmp:
            phoneme_dir = Path(tmp)
            (phoneme_dir / "take-001.wav").touch()
            (phoneme_dir / "take-002.wav").touch()
            state: dict = {"phonemes": {"sh": {"takes": []}}}
            self.assertEqual(next_take_id(phoneme_dir, state, "sh"), "take-003")

    def test_deleted_gap_does_not_rewind_counter(self) -> None:
        """002 was created then deleted; only 001 remains on disk and in
        state. The next id must be 003 — take-002 must never be reused.
        """
        with TemporaryDirectory() as tmp:
            phoneme_dir = Path(tmp)
            (phoneme_dir / "take-001.wav").touch()
            state: dict = {
                "phonemes": {
                    "sh": {
                        "keeper_take": None,
                        "max_take_id": 2,
                        "takes": [
                            {"id": "take-001"},
                        ],
                    }
                }
            }
            self.assertEqual(next_take_id(phoneme_dir, state, "sh"), "take-003")

    def test_highest_take_deleted_does_not_rewind_counter(self) -> None:
        """The bug the user hit: 001..004 exist, delete 004, then
        record. The next id must be 005, not 004.
        """
        with TemporaryDirectory() as tmp:
            phoneme_dir = Path(tmp)
            for n in (1, 2, 3):
                (phoneme_dir / f"take-{n:03d}.wav").touch()
            # 004 was created and then deleted — high-water mark stayed at 4.
            state: dict = {
                "phonemes": {
                    "sh": {
                        "keeper_take": None,
                        "max_take_id": 4,
                        "takes": [
                            {"id": "take-001"},
                            {"id": "take-002"},
                            {"id": "take-003"},
                        ],
                    }
                }
            }
            self.assertEqual(next_take_id(phoneme_dir, state, "sh"), "take-005")


if __name__ == "__main__":
    unittest.main()
