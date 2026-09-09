"""Independent integration/measurement tests; no model invocation."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hippo_eval.cli import (DEFAULT_CONFIG, METHODS, config_for, declared_configs,
                            experiment_succeeded, main, observe_hit, parse_methods, select_development,
                            validate_config)
from hippo_eval.contracts import body_digest, digest, load_json, write_json


class ParsingTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "input.json"
            for raw in ('{"id":1,"id":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":'):
                p.write_text(raw, encoding="utf-8")
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    load_json(p)

    def test_lossless_unicode_crlf_round_trip(self):
        value = {"body": "π\r\nA\0B\n雪"}
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "value.json"
            write_json(p, value)
            self.assertEqual(load_json(p), value)

    def test_compressed_evidence_is_deterministic_and_lossless(self):
        value = {"body": "雪\r\nEnd", "score": .125}
        with tempfile.TemporaryDirectory() as td:
            first, second = Path(td) / "a.json.gz", Path(td) / "b.json.gz"
            write_json(first, value)
            write_json(second, value)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(load_json(first), value)

    def test_truncated_compressed_evidence_is_a_clean_input_error(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "truncated.json.gz"
            write_json(p, {"result": "synthetic"})
            p.write_bytes(p.read_bytes()[:-4])
            with self.assertRaises(ValueError):
                load_json(p)

    def test_method_names_are_unique_and_known(self):
        self.assertEqual(parse_methods("lexical,bge"), ["lexical", "bge"])
        for value in ("", "lexical,lexical", "mock", "lexical, bge"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_methods(value)

    def test_configuration_resource_and_numeric_bounds(self):
        for key, value in (("k", True), ("k", 0), ("cpu_threads", 3),
                           ("max_rss_bytes", 2147483649), ("chunk_tokens", 1000),
                           ("overlap_tokens", 240), ("lexical_weight", float("nan"))):
            config = deepcopy(DEFAULT_CONFIG)
            config[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_config(config)

    def test_main_rejects_invalid_methods_without_execution(self):
        self.assertEqual(main(["run", "--methods", "mock", "--out", "unused"]), 2)

    def test_honest_failure_contract_is_not_experiment_success(self):
        bundle = {"analysis": {"valid": True}, "methods": [
            {"status": "EXECUTED", "queries": [{"status": "OK"}]},
            {"status": "NOT_RUN", "queries": []}]}
        self.assertFalse(experiment_succeeded(bundle))
        bundle["methods"][1] = {"status": "EXECUTED", "queries": [{"status": "ERROR"}]}
        self.assertFalse(experiment_succeeded(bundle))
        bundle["methods"][1]["queries"][0]["status"] = "OK"
        self.assertTrue(experiment_succeeded(bundle))

    def test_report_recomputes_and_rejects_forged_embedded_analysis(self):
        bundle = {"analysis": {"valid": True, "made_up_score": 1.0}}
        observed_analysis = {"valid": False, "errors": ["truncated raw results"]}
        with patch("hippo_eval.cli.load_json", return_value=bundle), \
             patch("hippo_eval.cli.read_fixtures", return_value=({}, {}, {})), \
             patch("hippo_eval.metrics.score_bundle", return_value=observed_analysis) as score, \
             patch("hippo_eval.reporting.write_reports") as report:
            self.assertEqual(main(["report", "supplied.json", "--out", "unused"]), 1)
            score.assert_called_once_with(bundle, {}, {})
            self.assertIs(report.call_args.args[1], observed_analysis)

    def test_compare_recomputes_both_raw_bundles(self):
        before = {"analysis": {"valid": True, "fake": 1}}
        after = {"analysis": {"valid": True, "fake": 2}}
        checked = {"valid": False}
        with patch("hippo_eval.cli.load_json", side_effect=[before, after]), \
             patch("hippo_eval.cli.read_fixtures", return_value=({}, {}, {})), \
             patch("hippo_eval.metrics.score_bundle", return_value=checked) as score, \
             patch("hippo_eval.metrics.compare_runs", return_value={"compatible": False}), \
             patch("hippo_eval.cli.write_json"):
            self.assertEqual(main(["compare", "a.json", "b.json", "--out", "unused"]), 1)
            self.assertEqual(score.call_count, 2)


class ObservationTests(unittest.TestCase):
    def test_full_fetch_hashes_observed_body_not_expected(self):
        record = {"id": "r1", "body": "Full retained body\r\nEnding",
                  "provenance": [{"source_id": "s", "revision": "v1", "availability": "retained"}],
                  "project": "P", "task": "T", "owner": "O", "status": "current",
                  "epistemic": "claimed", "revision": "v1"}
        query = {"rules": {"projects": ["P"], "tasks": None, "owners": ["O"],
                           "statuses": ["current"], "epistemics": ["claimed"],
                           "revisions": None, "require_evidence": True}}
        class BadAdapter:
            def fetch(self, record_id):
                actual = deepcopy(record)
                actual["body"] = "Full retained body"
                return actual
        result = observe_hit(BadAdapter(), {"record_id": "r1", "score": 1.0}, {"r1": record}, query)
        self.assertFalse(result["fidelity"]["passed"])
        self.assertIn("FULL_BODY_MISMATCH", result["fidelity"]["issues"])
        self.assertEqual(result["body_sha256"], body_digest("Full retained body"))
        self.assertNotEqual(result["body_sha256"], body_digest(record["body"]))

    def test_full_record_digest_detects_unchecked_metadata_changes(self):
        record = {"id": "r1", "body": "body", "title": "original", "level": 2,
                  "provenance": [], "project": "P", "task": "T", "owner": "O",
                  "status": "current", "epistemic": "claimed", "revision": "v1"}
        query = {"rules": {"projects": ["P"], "tasks": None, "owners": ["O"],
                           "statuses": ["current"], "epistemics": ["claimed"],
                           "revisions": None, "require_evidence": False}}
        class ChangedMetadata:
            def fetch(self, record_id):
                return dict(record, title="changed", level=3)
        result = observe_hit(ChangedMetadata(), {"record_id": "r1", "score": 1.0}, {"r1": record}, query)
        self.assertFalse(result["fidelity"]["passed"])
        self.assertIn("FULL_RECORD_MISMATCH", result["fidelity"]["issues"])
        self.assertNotEqual(result["record_sha256"], digest(record))


def development_bundles():
    bundles = []
    for config in declared_configs():
        cfg_digest = digest(config)
        analysis_methods = [{"name": name, "status": "EXECUTED", "valid": True,
                             "summary": {"ndcg_at_k": .8, "error_queries": 0, "unavailable_queries": 0}}
                            for name in METHODS]
        methods = [{"name": name, "identity": {"name": name, "model": "fixed-test-identity"},
                    "measurements": {"indexed_chunks": 40 if config["chunk_tokens"] == 240 else 60}}
                   for name in METHODS]
        bundles.append({"split": "development", "run_id": config["id"],
                        "supervision_required": True, "supervision_state": "COMPLETED",
                        "configuration": config, "configuration_digest": cfg_digest,
                        "identity": {"source_digest": "s", "fixture_digest": "f", "dependency_digest": "d", "metric_version": "m"},
                        "analysis": {"valid": True, "methods": analysis_methods}, "methods": methods})
    return bundles


class SelectionTests(unittest.TestCase):
    def test_predeclared_tie_break(self):
        selected = select_development(development_bundles())["selected"]
        self.assertEqual(selected["configuration"]["chunk_tokens"], 240)
        self.assertEqual(selected["configuration"]["lexical_weight"], 1.0)

    def test_material_quality_difference_beats_fewer_chunks(self):
        bundles = development_bundles()
        for method in bundles[0]["analysis"]["methods"]:
            method["summary"]["ndcg_at_k"] = .82
        selected = select_development(bundles)["selected"]
        self.assertEqual(selected["configuration"]["chunk_tokens"], 128)

    def test_holdout_source_drift_and_missing_methods_rejected(self):
        for mutate in (lambda bs: bs[0].update(split="heldout"),
                       lambda bs: bs[0]["identity"].update(source_digest="changed"),
                       lambda bs: bs[0]["analysis"]["methods"].pop(),
                       lambda bs: bs[0]["methods"][1]["identity"].update(model="changed"),
                       lambda bs: bs[0].update(supervision_state="PENDING"),
                       lambda bs: bs[0]["analysis"]["methods"][1]["summary"].update(error_queries=1)):
            bundles = development_bundles()
            mutate(bundles)
            with self.assertRaises(ValueError):
                select_development(bundles)


if __name__ == "__main__":
    unittest.main()
