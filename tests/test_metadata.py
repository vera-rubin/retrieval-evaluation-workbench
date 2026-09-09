"""Deterministic citation/deposit metadata checks, without account actions."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "generate_metadata.py"
PYTHON = str(Path(getattr(sys, "_base_executable", sys.executable)))


class MetadataDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)
        self.cff = self.path / "CITATION.cff"
        self.output = self.path / "description.md"
        self.cff.write_bytes((ROOT / "CITATION.cff").read_bytes())

    def invoke(self, expected, *options):
        result = subprocess.run(
            [PYTHON, "-I", "-S", str(GENERATOR), "--cff", str(self.cff),
             "--out", str(self.output), "--artifacts", str(ROOT / ".artifacts"),
             *options],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_generate_matches_authoritative_abstract(self):
        self.cff.write_text("abstract: |-\n  First paragraph.\n\n  AI use: disclosed.\n", encoding="utf-8")
        self.invoke(0)
        self.assertEqual(self.output.read_bytes(),
                         b"# Zenodo description\n\nFirst paragraph.\n\nAI use: disclosed.\n")

    def test_check_accepts_exact_description(self):
        self.invoke(0)
        before = self.output.read_bytes()
        result = self.invoke(0, "--check")
        self.assertIn("METADATA_DESCRIPTION_MATCHES", result.stdout)
        self.assertEqual(self.output.read_bytes(), before)

    def test_check_rejects_stale_description_without_overwriting(self):
        self.invoke(0)
        stale = self.output.read_bytes() + b"stale text\n"
        self.output.write_bytes(stale)
        result = self.invoke(1, "--check")
        self.assertIn("METADATA_DESCRIPTION_MISMATCH", result.stderr)
        self.assertEqual(self.output.read_bytes(), stale)

    def test_rejects_nonmapping_citation(self):
        self.cff.write_text("- not a mapping\n", encoding="utf-8")
        result = self.invoke(2)
        self.assertIn("must be a YAML mapping", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_duplicate_authority_keys(self):
        self.cff.write_text("abstract: first\nabstract: second\n", encoding="utf-8")
        result = self.invoke(2)
        self.assertIn("Duplicate YAML key: abstract", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_missing_description(self):
        self.cff.write_text("title: missing description\n", encoding="utf-8")
        result = self.invoke(2)
        self.assertIn("must provide a nonempty abstract", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_zenodo_json_override(self):
        (self.path / ".zenodo.json").write_text("{}", encoding="utf-8")
        result = self.invoke(2)
        self.assertIn("would override", result.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
