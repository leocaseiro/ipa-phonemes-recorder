# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Golden-file + MP3-property checks for the export pipeline.

These are the only automated tests for the pipeline (plan §5.1):
  • byte-exact manifest shape, because BaseSkill silently swallows
    any schema drift and no manual ear can catch it,
  • MP3 sample rate / channel count / total duration within a
    tolerance, because the bytes themselves are not reproducible
    across lame builds.

Run: python3.11 -m unittest tests.test_export
Requires: ffmpeg + ffprobe on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from server.export import export_bank

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_BANK = REPO_ROOT / "tests/fixtures/banks/en-test"
GOLDEN_DIR = REPO_ROOT / "tests/fixtures/golden"


def _which(name: str) -> Path:
    found = shutil.which(name)
    if not found:
        raise unittest.SkipTest(f"{name} not on PATH")
    return Path(found)


class ExportGoldenTest(unittest.TestCase):
    """The one automated pipeline check; pins the BaseSkill contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ffmpeg = _which("ffmpeg")
        _which("ffprobe")
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._work = Path(cls._tmpdir.name) / "en-test"
        shutil.copytree(FIXTURE_BANK, cls._work)
        config = json.loads((cls._work / "config.json").read_text(encoding="utf-8"))
        state = json.loads((cls._work / "state.json").read_text(encoding="utf-8"))
        cls.summary = export_bank(
            bank_path=cls._work,
            config=config,
            state=state,
            ffmpeg=cls.ffmpeg,
            tmp_root=Path(cls._tmpdir.name) / "ffmpeg_tmp",
            deterministic=True,
        )
        cls.mp3_path = cls._work / "dist/phonemes.mp3"
        cls.manifest_path = cls._work / "dist/phonemes.json"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def test_export_manifest_matches_golden(self) -> None:
        expected = (GOLDEN_DIR / "phonemes.json").read_text(encoding="utf-8")
        actual = self.manifest_path.read_text(encoding="utf-8")
        self.assertEqual(
            actual,
            expected,
            "Exported phonemes.json drifted from the golden file. If intentional, "
            "refresh tests/fixtures/golden/phonemes.json.",
        )

    def test_export_summary_counts(self) -> None:
        self.assertEqual(self.summary.phoneme_count, 3)
        self.assertEqual(self.summary.exported_count, 3)
        self.assertEqual(self.summary.skipped, [])

    def test_export_mp3_properties(self) -> None:
        meta = json.loads((GOLDEN_DIR / "phonemes-meta.json").read_text(encoding="utf-8"))

        stream = _ffprobe(self.mp3_path, entries="stream=codec_name,sample_rate,channels")
        self.assertEqual(stream["codec_name"], "mp3")
        self.assertEqual(int(stream["sample_rate"]), meta["sample_rate"])
        self.assertEqual(int(stream["channels"]), meta["channels"])

        fmt = _ffprobe(self.mp3_path, entries="format=duration")
        actual_ms = round(float(fmt["duration"]) * 1000)
        expected_ms = meta["total_duration_ms_expected"]
        tolerance = meta["mp3_duration_tolerance_ms"]
        delta = abs(actual_ms - expected_ms)
        self.assertLessEqual(
            delta,
            tolerance,
            f"MP3 duration {actual_ms} ms differs from expected {expected_ms} ms "
            f"by {delta} ms (tolerance {tolerance} ms).",
        )


def _ffprobe(path: Path, *, entries: str) -> dict[str, str]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", entries,
            "-of", "default=noprint_wrappers=1",
            str(path),
        ],
        text=True,
    )
    result: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


if __name__ == "__main__":
    unittest.main()
