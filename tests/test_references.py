# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for local reference resolution (Vocabulary + optional Wikimedia files)."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from server.references import ReferenceError, load_phoneme_reference_files, serve_reference


class ServeReferenceFileTest(unittest.TestCase):
    def test_vocabulary_map_before_ogg(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.ogg").write_bytes(b"og")
            (root / "b-1r9c1qm.mp3").write_bytes(b"mp3data")
            r = serve_reference(
                phoneme={"id": "b", "ipa": "b"},
                references_root=root,
                phoneme_reference_files={"b": "b-1r9c1qm.mp3"},
                attribution_path=root / "ATTRIBUTION.md",
            )
            self.assertEqual(r.body, b"mp3data")
            self.assertEqual(r.source, "vocabulary")

    def test_prefers_ogg_over_mp3_when_no_map(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "p.ogg").write_bytes(b"og")
            (root / "p.mp3").write_bytes(b"mp")
            (root / "ATTRIBUTION.md").write_text(
                "# Reference\n\n- p: me / CC0 / http://c\n", encoding="utf-8"
            )
            r = serve_reference(
                phoneme={"id": "p", "ipa": "p"},
                references_root=root,
                phoneme_reference_files={},
                attribution_path=root / "ATTRIBUTION.md",
            )
            self.assertEqual(r.body, b"og")
            self.assertIn("ogg", r.content_type)
            self.assertEqual(r.source, "wikimedia")

    def test_uses_vocabulary_map(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b-1r9c1qm.mp3").write_bytes(b"mp3data")
            r = serve_reference(
                phoneme={"id": "b", "ipa": "b"},
                references_root=root,
                phoneme_reference_files={"b": "b-1r9c1qm.mp3"},
                attribution_path=root / "nope",
            )
            self.assertEqual(r.body, b"mp3data")
            self.assertEqual(r.source, "vocabulary")

    def test_reference_missing_when_no_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ReferenceError) as ctx:
                serve_reference(
                    phoneme={"id": "p", "ipa": "p"},
                    references_root=root,
                    phoneme_reference_files={},
                    attribution_path=root / "ATTRIBUTION.md",
                )
            self.assertEqual(ctx.exception.code, "reference_missing")


class LoadPhonemeReferenceFilesTest(unittest.TestCase):
    def test_loads_seed_file(self) -> None:
        root = Path(__file__).resolve().parent.parent
        m = load_phoneme_reference_files(root / "server" / "seeds")
        self.assertIn("b", m)
        self.assertTrue(m["b"].endswith(".mp3"))


if __name__ == "__main__":
    unittest.main()
