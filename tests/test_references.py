# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for local reference resolution (PolyU + Vocabulary + Wikimedia)."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from server.references import (
    ReferenceError,
    load_phoneme_reference_files,
    load_phoneme_polyu_files,
    serve_reference,
)


class ServeReferenceFileTest(unittest.TestCase):
    def test_auto_prefers_polyu(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdir = root / "polyu"
            pdir.mkdir()
            (pdir / "B.mp3").write_bytes(b"poly")
            (root / "b-1r9c1qm.mp3").write_bytes(b"voc")
            r = serve_reference(
                phoneme={"id": "b", "ipa": "b"},
                references_root=root,
                phoneme_polyu_files={"b": "B.mp3"},
                phoneme_reference_files={"b": "b-1r9c1qm.mp3"},
                source="auto",
                attribution_path=root / "ATTRIBUTION.md",
            )
            self.assertEqual(r.body, b"poly")
            self.assertEqual(r.source, "polyu")

    def test_vocabulary_only_skips_polyu(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdir = root / "polyu"
            pdir.mkdir()
            (pdir / "B.mp3").write_bytes(b"poly")
            (root / "b-1r9c1qm.mp3").write_bytes(b"voc")
            r = serve_reference(
                phoneme={"id": "b", "ipa": "b"},
                references_root=root,
                phoneme_polyu_files={"b": "B.mp3"},
                phoneme_reference_files={"b": "b-1r9c1qm.mp3"},
                source="vocabulary",
                attribution_path=root / "ATTRIBUTION.md",
            )
            self.assertEqual(r.body, b"voc")
            self.assertEqual(r.source, "vocabulary")

    def test_polyu_only_fails_if_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ReferenceError) as ctx:
                serve_reference(
                    phoneme={"id": "b", "ipa": "b"},
                    references_root=root,
                    phoneme_polyu_files={"b": "B.mp3"},
                    phoneme_reference_files={},
                    source="polyu",
                    attribution_path=root / "ATTRIBUTION.md",
                )
            self.assertEqual(ctx.exception.code, "reference_missing")

    def test_prefers_ogg_wikimedia_when_no_map_vocabulary(self) -> None:
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
                phoneme_polyu_files={},
                phoneme_reference_files={},
                source="vocabulary",
                attribution_path=root / "ATTRIBUTION.md",
            )
            self.assertEqual(r.body, b"og")
            self.assertIn("ogg", r.content_type)
            self.assertEqual(r.source, "wikimedia")

    def test_reference_missing_auto(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ReferenceError) as ctx:
                serve_reference(
                    phoneme={"id": "p", "ipa": "p"},
                    references_root=root,
                    phoneme_polyu_files={},
                    phoneme_reference_files={},
                    source="auto",
                    attribution_path=root / "ATTRIBUTION.md",
                )
            self.assertEqual(ctx.exception.code, "reference_missing")


class LoadSeedsTest(unittest.TestCase):
    def test_loads_phoneme_reference_files(self) -> None:
        root = Path(__file__).resolve().parent.parent
        m = load_phoneme_reference_files(root / "server" / "seeds")
        self.assertIn("b", m)
        self.assertTrue(m["b"].endswith(".mp3"))

    def test_loads_phoneme_polyu_files(self) -> None:
        root = Path(__file__).resolve().parent.parent
        m = load_phoneme_polyu_files(root / "server" / "seeds")
        self.assertIn("b", m)
        self.assertTrue(m["b"].endswith(".mp3"))


if __name__ == "__main__":
    unittest.main()
