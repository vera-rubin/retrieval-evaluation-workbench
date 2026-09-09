"""Standalone export, provenance and bounded reproduction regressions."""
from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from hippo_eval import cli
from hippo_eval.contracts import digest, load_json, write_json
from hippo_eval.metrics import _check_identity
from hippo_eval.scenarios import check_traces

ROOT = Path(__file__).resolve().parents[1]


class ReproductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "declaration.json"
        self.args = argparse.Namespace(corpus=ROOT / "fixtures/corpus.json",
                                      queries=ROOT / "fixtures/queries.json",
                                      out=self.path, artifacts=ROOT / ".artifacts",
                                      reproduction=self.path, frozen=None,
                                      config=None, split="development")
        self.corpus = load_json(self.args.corpus)
        self.queries = load_json(self.args.queries)
        self.manifest = cli.prepare_reproduction(self.args)

    def test_fixed_protocol_allows_both_known_splits(self):
        for split in ("development", "heldout"):
            self.args.split = split
            config = cli.config_for(self.args, self.corpus, self.queries)
            self.assertEqual(config["chunk_tokens"], 240)
            self.assertEqual(config["lexical_weight"], 1.0)
            self.assertEqual(config["overlap_tokens"], 32)
        self.assertTrue(self.manifest["original_heldout_already_known"])
        self.assertFalse(self.manifest["selection_performed"])
        self.assertNotIn("holdout_used", self.manifest)

    def test_reproduction_preserves_existing_declaration(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            cli.prepare_reproduction(self.args)

    def test_false_new_blind_claim_is_rejected(self):
        self.manifest["original_heldout_already_known"] = False
        write_json(self.path, self.manifest)
        with self.assertRaisesRegex(ValueError, "known-split"):
            cli.config_for(self.args, self.corpus, self.queries)

    def test_modified_configuration_is_rejected(self):
        self.manifest["configuration"]["lexical_weight"] = 2.0
        self.manifest["configuration_digest"] = digest(self.manifest["configuration"])
        write_json(self.path, self.manifest)
        with self.assertRaisesRegex(ValueError, "fixed historical protocol"):
            cli.config_for(self.args, self.corpus, self.queries)

    def test_stale_source_identity_is_rejected(self):
        self.manifest["source_digest"] = "0" * 64
        write_json(self.path, self.manifest)
        with self.assertRaisesRegex(ValueError, "source_digest"):
            cli.config_for(self.args, self.corpus, self.queries)

    def test_stale_dependency_identity_is_rejected(self):
        self.manifest["dependency_digest"] = "0" * 64
        write_json(self.path, self.manifest)
        with self.assertRaisesRegex(ValueError, "dependency_digest"):
            cli.config_for(self.args, self.corpus, self.queries)

    def test_fixture_transformation_invalidates_declaration(self):
        changed = deepcopy(self.corpus)
        changed["version"] = "deliberate-change"
        with self.assertRaisesRegex(ValueError, "fixture identity"):
            cli.config_for(self.args, changed, self.queries)

    def test_model_revision_change_is_rejected(self):
        self.manifest["model_specs"]["bge"]["revision"] = "0" * 40
        write_json(self.path, self.manifest)
        with self.assertRaisesRegex(ValueError, "model specifications"):
            cli.config_for(self.args, self.corpus, self.queries)

    def test_configuration_inputs_are_mutually_exclusive(self):
        self.args.config = self.path
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            cli.config_for(self.args, self.corpus, self.queries)


class PortableEvidenceTests(unittest.TestCase):
    def test_archive_identity_uses_actual_source_hashes_without_invented_commit(self):
        with patch("hippo_eval.cli.subprocess.check_output", side_effect=FileNotFoundError):
            identity = cli.source_identity()
        identity["fixture_digest"] = "1" * 64
        errors = []
        _check_identity(identity, errors)
        self.assertEqual(errors, [])
        self.assertIsNone(identity["git_head"])
        self.assertEqual(identity["source_origin"], "source_archive")
        self.assertEqual(identity["source_digest"], digest(identity["source_files"]))
        self.assertNotIn(str(ROOT), json.dumps(identity))

    def test_parent_git_checkout_is_not_inherited(self):
        with patch("hippo_eval.cli.subprocess.check_output", return_value=str(ROOT.parent)):
            identity = cli.source_identity()
        self.assertIsNone(identity["git_head"])

    def test_archive_identity_still_rejects_tampered_source(self):
        with patch("hippo_eval.cli.subprocess.check_output", side_effect=FileNotFoundError):
            identity = cli.source_identity()
        identity["fixture_digest"] = "1" * 64
        identity["source_digest"] = "0" * 64
        errors = []
        _check_identity(identity, errors)
        self.assertTrue(any("does not match source_files" in error for error in errors))

    def test_diagnostics_keep_filename_and_omit_local_root(self):
        text = f'Missing model file "{ROOT / ".artifacts/models/example/config.json"}"'
        result = cli.portable_diagnostic(text)
        self.assertNotIn(str(ROOT), result)
        self.assertIn("<ARTIFACTS>", result)
        self.assertIn("config.json", result)


class PublicTraceAuthorshipTests(unittest.TestCase):
    def test_model_authored_literal_traces_are_explicitly_supported(self):
        scenarios = load_json(ROOT / "scenarios/cases.json")
        traces = load_json(ROOT / "scenarios/correct.json")
        self.assertEqual(traces["authorship"]["method"], "model_authored_literal_examples")
        result = check_traces(scenarios, traces)
        self.assertTrue(result["valid"], result["errors"])
        self.assertNotIn("hand_authored", result["execution"])

    def test_authorship_does_not_replace_required_review_note(self):
        scenarios = load_json(ROOT / "scenarios/cases.json")
        traces = load_json(ROOT / "scenarios/correct.json")
        traces["authorship"]["review"] = ""
        result = check_traces(scenarios, traces)
        self.assertFalse(result["valid"])
        self.assertTrue(any("authorship" in error for error in result["errors"]))


class StagingLockTests(unittest.TestCase):
    def test_committed_lock_and_declared_closure_match_without_network(self):
        spec = importlib.util.spec_from_file_location("publication_stage_cpu", ROOT / "staging/stage_cpu.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        locked = module.read_lock()
        self.assertEqual(len(locked), 29)
        self.assertEqual(module.RECEIPTS, module.ARTIFACTS / "receipts")
        self.assertTrue(all(len(hash_value) == 64 for _, hash_value in locked.values()))
