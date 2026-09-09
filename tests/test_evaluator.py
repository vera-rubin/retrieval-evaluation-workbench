"""Independent arithmetic/contract/trace checks; no models or product broker."""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from hippo_eval.contracts import METRIC_VERSION, RUN_SCHEMA, body_digest, digest, load_json
from hippo_eval.metrics import compare_runs, score_bundle
from hippo_eval.reporting import write_reports
from hippo_eval.scenarios import check_traces

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    records = []
    for record_id, owner, status, body in (("A", "alice", "current", "Café\n猫"),
                                           ("B", "alice", "current", "second relevant fact"),
                                           ("C", "alice", "current", "an unrelated distractor"),
                                           ("D", "bob", "current", "private to Bob"),
                                           ("E", "alice", "revoked", "old revoked fact")):
        records.append({"id": record_id, "family": "dev", "project": "p", "task": "t", "owner": owner,
                        "level": 2, "kind": "belief", "status": status, "epistemic": "claimed", "revision": "r1",
                        "title": f"Title {len(records)}", "body": body, "body_sha256": body_digest(body),
                        "provenance": [{"source_id": "receipt-" + record_id, "revision": "r1", "availability": "retained"}],
                        "supersedes": []})
    rules = {"projects": ["p"], "owners": ["alice"], "tasks": ["t"], "statuses": ["current"],
             "epistemics": ["claimed"], "revisions": ["r1"], "require_evidence": True}
    queries = [{"id": "q", "split": "development", "family": "dev", "category": "facts", "text": "Which facts?",
                "relevance": {"A": 3, "B": 1}, "rationale": "A is exact, B is supporting; C is irrelevant.", "answerable": True, "rules": rules},
               {"id": "none", "split": "development", "family": "dev", "category": "negative", "text": "A fact absent from this corpus?",
                "relevance": {}, "rationale": "No relevant record.", "answerable": False, "rules": copy.deepcopy(rules)}]
    return ({"schema": "hippo-corpus/v1", "version": "unit-independent", "authorship": {"method": "model_authored_literal_examples"}, "records": records},
            {"schema": "hippo-queries/v1", "version": "unit-independent", "authorship": {"method": "model_authored_literal_examples"}, "queries": queries})


def ranked(record, score):
    return {"record_id": record["id"], "score": score, "body_sha256": body_digest(record["body"]),
            "record_sha256": digest(record),
            "provenance_sha256": digest(record["provenance"]),
            "observed": {key: record[key] for key in ("project", "task", "owner", "status", "epistemic", "revision")},
            "fidelity": {"passed": True, "issues": []}}


def run(corpus, queries, order=("C", "A", "B"), negative=()):
    records = {record["id"]: record for record in corpus["records"]}
    config = {"k": 3, "chunk_tokens": 240, "overlap_tokens": 32, "seed": 17}
    sources = {"hippo_eval/unit_source.py": digest("synthetic source identity")}
    dependencies = {"python": "test-version"}
    observations = []
    for query_id, ids, elapsed in (("q", order, 10.0), ("none", negative, 20.0)):
        observations.append({"query_id": query_id, "status": "OK", "elapsed_ms": elapsed, "errors": [],
                             "ranked": [ranked(records[record_id], float(len(ids) - index)) for index, record_id in enumerate(ids)]})
    return {"schema": RUN_SCHEMA, "run_id": "unit-run", "created_at": "2026-09-06T00:00:00Z",
            "execution": "executed_local_synthetic", "split": "development", "integrity_errors": [],
            "identity": {"source_files": sources, "source_digest": digest(sources), "git_head": "a" * 40,
                         "fixture_digest": digest({"corpus": corpus, "queries": queries}),
                         "dependencies": dependencies, "dependency_digest": digest(dependencies), "metric_version": METRIC_VERSION},
            "configuration": config, "configuration_digest": digest(config),
            "methods": [{"name": "lexical", "status": "EXECUTED", "identity": {"backend": "unit-observations", "version": "1"},
                         "configuration_digest": digest(config), "errors": [],
                         "measurements": {"load_ms": 1.0, "index_ms": 2.0, "query_latency_ms": [10.0, 20.0], "peak_rss_bytes": 4096},
                         "queries": observations}]}


class MetricArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.corpus, self.queries = fixture()
        self.bundle = run(self.corpus, self.queries)

    def score(self):
        return score_bundle(self.bundle, self.corpus, self.queries)

    def test_independent_graded_ranking_arithmetic(self):
        analysis = self.score()
        self.assertTrue(analysis["valid"], analysis)
        summary = analysis["methods"][0]["summary"]
        self.assertEqual(summary["recall_at_k"], 1.0)
        self.assertAlmostEqual(summary["precision_at_k"], 2 / 3)
        self.assertEqual(summary["mrr"], .5)
        # Literal gains/positions, independent of evaluator implementation.
        self.assertAlmostEqual(summary["ndcg_at_k"], (7 / math.log2(3) + .5) / (7 + 1 / math.log2(3)))
        self.assertAlmostEqual(summary["precision_at_k_oracle_ceiling"], 2 / 3)
        self.assertEqual(summary["answerable_queries"], 1)
        self.assertEqual(summary["unanswerable_abstained"], 1)
        self.assertEqual(summary["latency"]["p50_ms"], 15)
        self.assertEqual(summary["latency"]["p95_ms"], 20)
        query = analysis["methods"][0]["queries"][0]
        self.assertEqual(query["eligible_record_count"], 3)
        self.assertEqual(query["eligible_distractor_count"], 1)
        self.assertEqual(query["missing_relevant_ids"], [])
        self.assertTrue(any("Sparse" in warning for warning in analysis["warnings"]))

    def test_empty_results_are_valid_and_zero(self):
        self.bundle = run(self.corpus, self.queries, ())
        analysis = self.score()
        self.assertTrue(analysis["valid"], analysis)
        summary = analysis["methods"][0]["summary"]
        for key in ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k"):
            self.assertEqual(summary[key], 0)
        self.assertEqual(analysis["methods"][0]["queries"][0]["missing_relevant_ids"], ["A", "B"])

    def test_precision_uses_k_not_returned_count(self):
        self.bundle = run(self.corpus, self.queries, ("A",))
        summary = self.score()["methods"][0]["summary"]
        self.assertEqual(summary["recall_at_k"], .5)
        self.assertEqual(summary["precision_at_k"], 1 / 3)

    def test_negative_false_positives_are_separate(self):
        self.bundle = run(self.corpus, self.queries, ("A", "B"), ("C",))
        summary = self.score()["methods"][0]["summary"]
        self.assertEqual(summary["recall_at_k"], 1)
        self.assertEqual(summary["unanswerable_false_positive_queries"], 1)
        self.assertEqual(summary["unanswerable_returned_records"], 1)
        self.assertEqual(summary["unanswerable_abstention_rate"], 0)

    def test_explicit_error_is_zero_quality_not_dropped(self):
        query = self.bundle["methods"][0]["queries"][0]
        query.update(status="ERROR", errors=["synthetic retrieval failed"], ranked=[])
        analysis = self.score()
        self.assertTrue(analysis["valid"], analysis)
        self.assertEqual(analysis["methods"][0]["summary"]["recall_at_k"], 0)
        self.assertEqual(analysis["methods"][0]["summary"]["error_queries"], 1)

    def test_unavailable_negative_is_not_successful_abstention(self):
        query = self.bundle["methods"][0]["queries"][1]
        query.update(status="UNAVAILABLE", errors=["index unavailable"])
        analysis = self.score()
        self.assertTrue(analysis["valid"], analysis)
        self.assertEqual(analysis["methods"][0]["summary"]["unanswerable_abstained"], 0)
        self.assertEqual(analysis["methods"][0]["summary"]["unavailable_queries"], 1)


class ResultValidationTests(unittest.TestCase):
    setUp = MetricArithmeticTests.setUp
    score = MetricArithmeticTests.score
    # Each assertion mutates an observed bundle, not the fixture oracle.
    def invalid(self, fragment):
        analysis = self.score()
        self.assertFalse(analysis["valid"])
        self.assertIsNone(analysis["methods"][0]["summary"])
        errors = analysis["errors"] + analysis["methods"][0]["errors"]
        self.assertTrue(any(fragment in error for error in errors), errors)
        return analysis

    def test_truncated_results_fail(self):
        self.bundle["methods"][0]["queries"].pop()
        self.invalid("incomplete/mixed split")

    def test_missing_ranked_is_not_an_empty_success(self):
        del self.bundle["methods"][0]["queries"][0]["ranked"]
        self.invalid("ranked must be an array")

    def test_duplicate_record_ids_fail(self):
        items = self.bundle["methods"][0]["queries"][0]["ranked"]
        items[1] = copy.deepcopy(items[0])
        self.invalid("duplicate record ID")

    def test_duplicate_query_ids_fail(self):
        self.bundle["methods"][0]["queries"][1] = copy.deepcopy(self.bundle["methods"][0]["queries"][0])
        self.invalid("duplicate query ID")

    def test_duplicate_method_ids_fail(self):
        self.bundle["methods"].append(copy.deepcopy(self.bundle["methods"][0]))
        self.invalid("duplicate method name")

    def test_unknown_id_fail(self):
        self.bundle["methods"][0]["queries"][0]["ranked"][0]["record_id"] = "fabricated"
        self.invalid("unknown record ID")

    def test_nonfinite_and_bool_scores_fail(self):
        for value in (float("nan"), float("inf"), True):
            with self.subTest(value=value):
                self.bundle["methods"][0]["queries"][0]["ranked"][0]["score"] = value
                self.invalid("finite number")

    def test_score_order_fail(self):
        self.bundle["methods"][0]["queries"][0]["ranked"][1]["score"] = 999.0
        self.invalid("non-increasing")

    def test_unhashable_id_reports_error_without_crashing(self):
        self.bundle["methods"][0]["queries"][0]["ranked"][0]["record_id"] = ["bad"]
        self.invalid("record_id")

    def test_wrong_owner_scope_fails(self):
        self.bundle = run(self.corpus, self.queries, ("D",))
        analysis = self.invalid("violates scope/status/evidence")
        self.assertEqual(analysis["methods"][0]["diagnostics"]["scope_rule_violations"], 1)

    def test_revoked_record_fails(self):
        self.bundle = run(self.corpus, self.queries, ("E",))
        self.invalid("violates scope/status/evidence")

    def test_wrong_observed_status_and_revision_fail(self):
        item = self.bundle["methods"][0]["queries"][0]["ranked"][0]
        item["observed"]["status"] = "superseded"
        item["observed"]["revision"] = "r0"
        analysis = self.invalid("observed.status")
        self.assertEqual(analysis["methods"][0]["diagnostics"]["observed_revision_mismatches"], 1)

    def test_wrong_provenance_fails(self):
        self.bundle["methods"][0]["queries"][0]["ranked"][0]["provenance_sha256"] = "f" * 64
        analysis = self.invalid("provenance_sha256")
        self.assertEqual(analysis["methods"][0]["diagnostics"]["provenance_mismatches"], 1)

    def test_wrong_full_body_fails_even_with_passed_flag(self):
        self.bundle["methods"][0]["queries"][0]["ranked"][0]["body_sha256"] = body_digest("truncated")
        self.invalid("full fetched body")

    def test_complete_record_digest_catches_title_level_and_extra_fields(self):
        original = self.corpus["records"][2]
        for change in ({"title": "altered"}, {"level": 3}, {"unexpected_entity": "invented"}):
            with self.subTest(change=change):
                changed = {**original, **change}
                self.bundle["methods"][0]["queries"][0]["ranked"][0]["record_sha256"] = digest(changed)
                analysis = self.invalid("complete fetched record")
                self.assertEqual(analysis["methods"][0]["diagnostics"]["complete_record_mismatches"], 1)

    def test_missing_complete_record_digest_fails(self):
        del self.bundle["methods"][0]["queries"][0]["ranked"][0]["record_sha256"]
        self.invalid("record_sha256")

    def test_executed_method_errors_are_not_hidden(self):
        self.bundle["methods"][0]["errors"] = ["unclassified method failure"]
        self.invalid("EXECUTED method cannot")

    def test_malformed_method_error_reasons_fail(self):
        self.bundle["methods"][0]["errors"] = [42]
        self.invalid("diagnostic strings")

    def test_fidelity_flag_cannot_hide_issues(self):
        self.bundle["methods"][0]["queries"][0]["ranked"][0]["fidelity"]["issues"] = ["source differs"]
        self.invalid("fidelity")

    def test_wrong_method_configuration_identity_fails(self):
        self.bundle["methods"][0]["configuration_digest"] = "f" * 64
        self.invalid("mixed configuration")

    def test_wrong_bundle_configuration_digest_fails(self):
        self.bundle["configuration"]["seed"] = 18
        self.invalid("configuration_digest")

    def test_in_run_integrity_change_fails(self):
        self.bundle["integrity_errors"] = ["source changed during run"]
        self.invalid("source changed during run")

    def test_fixture_mismatch_fails(self):
        self.bundle["identity"]["fixture_digest"] = "0" * 64
        self.invalid("fixture_digest")

    def test_missing_error_reason_fails(self):
        self.bundle["methods"][0]["queries"][0].update(status="ERROR", ranked=[])
        self.invalid("explicit reason")

    def test_error_with_ranked_output_fails(self):
        self.bundle["methods"][0]["queries"][0].update(status="ERROR", errors=["failed"])
        self.invalid("cannot contain ranked")

    def test_unknown_query_status_fails(self):
        self.bundle["methods"][0]["queries"][0]["status"] = "SUCCESS"
        self.invalid("unsupported query status")

    def test_latency_identity_fails(self):
        self.bundle["methods"][0]["measurements"]["query_latency_ms"][0] = 11
        self.invalid("differs from measurement")

    def test_not_run_has_no_quality(self):
        method = self.bundle["methods"][0]
        method.update(status="NOT_RUN", queries=[], errors=["model is absent"], measurements={"load_ms": None, "index_ms": None, "query_latency_ms": []})
        analysis = self.score()
        self.assertTrue(analysis["valid"], analysis)
        self.assertIsNone(analysis["methods"][0]["summary"])
        method["measurements"]["load_ms"] = 0
        self.invalid("NOT_RUN requires explicit null")

    def test_failed_partial_execution_has_no_quality(self):
        self.bundle["methods"][0].update(status="FAILED", errors=["synthetic resource guard"], queries=[])
        analysis = self.score()
        self.assertTrue(analysis["valid"], analysis)
        self.assertIsNone(analysis["methods"][0]["summary"])

    def test_unicode_chunk_provenance_checked_independently(self):
        self.bundle = run(self.corpus, self.queries, ("A",))
        item = self.bundle["methods"][0]["queries"][0]["ranked"][0]
        item["chunk_ids"] = ["A-body-3"]
        item["chunks"] = [{"chunk_id": "A-body-3", "record_id": "A", "field": "body",
                           "char_start": 3, "char_end": 6, "byte_start": 3, "byte_end": 9,
                           "token_count": 5, "text": "é\n猫", "text_sha256": body_digest("é\n猫"),
                           "source_field_sha256": body_digest("Café\n猫")}]
        self.assertTrue(self.score()["valid"])
        item["chunks"][0]["byte_end"] = 6
        self.invalid("UTF-8 byte offsets mismatch")

    def test_malformed_fixture_does_not_crash(self):
        self.corpus["records"][0]["provenance"] = [42]
        self.bundle["identity"]["fixture_digest"] = digest({"corpus": self.corpus, "queries": self.queries})
        self.invalid("malformed provenance")


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.corpus, self.queries = fixture()
        self.old_bundle = run(self.corpus, self.queries, ("A", "B", "C"))
        self.new_bundle = run(self.corpus, self.queries, ("C", "B", "A"))

    def compare(self):
        return compare_runs(score_bundle(self.old_bundle, self.corpus, self.queries), score_bundle(self.new_bundle, self.corpus, self.queries))

    def test_same_identity_detects_rank_regression(self):
        result = self.compare()
        self.assertTrue(result["compatible"], result)
        self.assertTrue(result["regressed"])
        self.assertLess(result["methods"][0]["deltas"]["ndcg_at_k"], 0)
        self.assertEqual(result["methods"][0]["deltas"]["recall_at_k"], 0)

    def test_source_change_is_allowed(self):
        sources = {"hippo_eval/unit_source.py": digest("new source")}
        self.new_bundle["identity"].update(source_files=sources, source_digest=digest(sources), git_head="b" * 40)
        result = self.compare()
        self.assertTrue(result["compatible"], result)
        self.assertTrue(result["source_changed"])

    def test_dependency_change_is_incompatible(self):
        versions = {"python": "different-version"}
        self.new_bundle["identity"].update(dependencies=versions, dependency_digest=digest(versions))
        result = self.compare()
        self.assertFalse(result["compatible"])
        self.assertIn("incompatible identity.dependency_digest", result["reasons"])
        self.assertEqual(result["methods"][0]["deltas"], {})

    def test_model_identity_change_is_incompatible(self):
        self.new_bundle["methods"][0]["identity"]["version"] = "2"
        result = self.compare()
        self.assertFalse(result["compatible"])
        self.assertEqual(result["methods"][0]["deltas"], {})

    def test_configuration_change_is_not_a_regression_comparison(self):
        self.new_bundle["configuration"]["seed"] = 18
        changed = digest(self.new_bundle["configuration"])
        self.new_bundle["configuration_digest"] = changed
        self.new_bundle["methods"][0]["configuration_digest"] = changed
        self.assertFalse(self.compare()["compatible"])

    def test_invalid_observation_cannot_produce_regression_deltas(self):
        self.new_bundle["methods"][0]["queries"].pop()
        result = self.compare()
        self.assertFalse(result["compatible"])
        self.assertIsNone(result["regressed"])
        self.assertEqual(result["methods"][0]["deltas"], {})


class ResourceReceiptTests(unittest.TestCase):
    def setUp(self):
        self.corpus, self.queries = fixture()
        self.bundle = run(self.corpus, self.queries)
        self.bundle["configuration"]["max_rss_bytes"] = 2147483648
        config_hash = digest(self.bundle["configuration"])
        self.bundle["configuration_digest"] = config_hash
        self.bundle["methods"][0]["configuration_digest"] = config_hash
        self.bundle["identity"]["dependencies"]["python_executable_sha256"] = digest("synthetic interpreter")
        self.bundle["identity"]["dependency_digest"] = digest(self.bundle["identity"]["dependencies"])
        self.bundle["supervision_required"] = True
        self.bundle["execution_runtime"] = {"pid": 123, "isolated": True, "no_site": True, "executable_name": "python.exe"}
        self.bundle["resource"] = {"peak_rss_bytes": 4096, "rss_samples": 3, "sample_interval_ms": 100,
                                   "elapsed_ms": 300, "limit_bytes": 2147483648, "failure": None,
                                   "child_exit_code": 0, "monitored_pid": 123,
                                   "scope": "direct_base_interpreter_owned_inference_process_only"}

    def test_matching_resource_receipt_passes_as_sampled_evidence(self):
        result = score_bundle(self.bundle, self.corpus, self.queries)
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["resource_validation"]["passed"])

    def test_missing_required_guard_fails(self):
        del self.bundle["resource"]
        result = score_bundle(self.bundle, self.corpus, self.queries)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["methods"][0]["summary"])

    def test_guard_failures_and_numeric_bounds_fail(self):
        cases = ({"failure": "RSS_LIMIT"}, {"child_exit_code": 1}, {"rss_samples": 0},
                 {"sample_interval_ms": 0}, {"monitored_pid": 124}, {"limit_bytes": 100},
                 {"peak_rss_bytes": 2147483649}, {"peak_rss_bytes": float("nan")})
        for change in cases:
            with self.subTest(change=change):
                bundle = copy.deepcopy(self.bundle)
                bundle["resource"].update(change)
                result = score_bundle(bundle, self.corpus, self.queries)
                self.assertFalse(result["valid"], result)
                self.assertFalse(result["resource_validation"]["passed"])

    def test_supplied_optional_receipt_is_still_validated(self):
        self.bundle["supervision_required"] = False
        self.bundle["resource"]["failure"] = "RSS_LIMIT"
        self.assertFalse(score_bundle(self.bundle, self.corpus, self.queries)["valid"])

    def test_wrong_runtime_isolation_fails(self):
        self.bundle["execution_runtime"]["no_site"] = False
        self.assertFalse(score_bundle(self.bundle, self.corpus, self.queries)["valid"])

    def test_declared_limit_cannot_exceed_two_gib(self):
        self.bundle["configuration"]["max_rss_bytes"] = 3 * 1024 ** 3
        changed = digest(self.bundle["configuration"])
        self.bundle["configuration_digest"] = changed
        self.bundle["methods"][0]["configuration_digest"] = changed
        self.bundle["resource"]["limit_bytes"] = 3 * 1024 ** 3
        self.assertFalse(score_bundle(self.bundle, self.corpus, self.queries)["valid"])

    def test_comparison_rechecks_resource_outcome(self):
        old = score_bundle(self.bundle, self.corpus, self.queries)
        new = copy.deepcopy(old)
        new["resource"]["failure"] = "changed after scoring"
        result = compare_runs(old, new)
        self.assertFalse(result["compatible"])
        self.assertEqual(result["methods"][0]["deltas"], {})


class RegressionAnalysisValidationTests(unittest.TestCase):
    setUp = RegressionTests.setUp
    compare = RegressionTests.compare

    def test_truncated_analysis_cannot_claim_valid(self):
        old = score_bundle(self.old_bundle, self.corpus, self.queries)
        new = score_bundle(self.new_bundle, self.corpus, self.queries)
        new["methods"][0]["queries"].pop()
        result = compare_runs(old, new)
        self.assertFalse(result["compatible"])
        self.assertEqual(result["methods"][0]["deltas"], {})

    def test_tampered_aggregate_cannot_claim_valid(self):
        old = score_bundle(self.old_bundle, self.corpus, self.queries)
        new = score_bundle(self.new_bundle, self.corpus, self.queries)
        new["methods"][0]["summary"]["recall_at_k"] = .99
        result = compare_runs(old, new)
        self.assertFalse(result["compatible"])
        self.assertEqual(result["methods"][0]["deltas"], {})

    def test_malformed_analysis_returns_incompatible(self):
        for value in (None, {}, {"valid": True, "methods": ["oops"]}):
            with self.subTest(value=value):
                self.assertFalse(compare_runs(value, value)["compatible"])

    def test_not_run_is_not_a_zero_quality_baseline(self):
        method = self.old_bundle["methods"][0]
        method.update(status="NOT_RUN", queries=[], errors=["not executed"], measurements={"load_ms": None, "index_ms": None, "query_latency_ms": []})
        result = self.compare()
        self.assertTrue(result["compatible"], result)
        self.assertFalse(result["methods"][0]["comparable"])
        self.assertIsNone(result["regressed"])


class ReportingTests(unittest.TestCase):
    def test_static_reports_escape_all_untrusted_text(self):
        corpus, queries = fixture()
        attack = '<script>alert("x")</script> [x](javascript:alert(1)) | <img src=x onerror=alert(2)>'
        queries["queries"][0]["text"] = attack
        queries["queries"][0]["rationale"] = attack
        bundle = run(corpus, queries)
        analysis = score_bundle(bundle, corpus, queries)
        with tempfile.TemporaryDirectory(prefix="report-unit-", dir=ROOT) as directory:
            paths = write_reports(bundle, analysis, directory)
            self.assertEqual(set(paths), {"json", "markdown", "html"})
            html = Path(paths["html"]).read_text(encoding="utf-8")
            md = Path(paths["markdown"]).read_text(encoding="utf-8")
            self.assertNotIn("<script>", html)
            self.assertNotIn("<img", html)
            self.assertNotIn("<script>", md)
            self.assertNotIn("[x](javascript", md)
            self.assertIn("&lt;script&gt;", html)
            self.assertIn("Content-Security-Policy", html)
            self.assertIn("production persistence and live recovery are outside this experiment", html)
            self.assertIn("Missing relevant IDs", html)
            self.assertIn("Precision ceiling", html)
            self.assertIn("full_fetch_checks", html)
            self.assertIn("model_identity", html)
            parsed = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(parsed["analysis"]["methods"][0]["queries"][0]["text"], attack)
            self.assertNotIn("run", parsed)

    def test_invalid_nonfinite_measurement_report_remains_valid_json(self):
        corpus, queries = fixture()
        bundle = run(corpus, queries)
        bundle["methods"][0]["measurements"]["load_ms"] = float("nan")
        analysis = score_bundle(bundle, corpus, queries)
        self.assertFalse(analysis["valid"])
        with tempfile.TemporaryDirectory(prefix="report-invalid-", dir=ROOT) as directory:
            paths = write_reports(bundle, analysis, directory)
            data = load_json(paths["json"])
            self.assertTrue(data["serialization_warnings"])
            self.assertFalse(data["analysis"]["valid"])

    def test_output_cannot_escape_workbench(self):
        corpus, queries = fixture()
        bundle = run(corpus, queries)
        with self.assertRaises(ValueError):
            write_reports(bundle, score_bundle(bundle, corpus, queries), ROOT.parent / "forbidden-unit-output")


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        self.scenarios = load_json(ROOT / "scenarios" / "cases.json")
        self.correct = load_json(ROOT / "scenarios" / "correct.json")
        self.incorrect = load_json(ROOT / "scenarios" / "incorrect.json")

    def test_hand_correct_trace_matches_35_observations(self):
        result = check_traces(self.scenarios, self.correct)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["summary"]["passed"], 12)
        self.assertEqual(sum(len(case["steps"]) for case in result["cases"]), 35)
        self.assertTrue(all(value == "NOT RUN" for value in result["product_execution"].values()))

    def test_each_deliberate_bad_case_detected(self):
        result = check_traces(self.scenarios, self.incorrect)
        self.assertFalse(result["valid"])
        self.assertTrue(result["summary"]["schema_valid"])
        self.assertEqual(result["summary"]["failed"], 12)
        self.assertEqual({case["id"] for case in result["cases"] if not case["passed"]}, {f"S{number:02d}" for number in range(1, 13)})
        # Independently enumerated defects, not generated from oracle values.
        expected_paths = ("S01.same_event_new_operation.record_ids", "S02.interrupted_before_commit.record_ids",
                          "S03.mechanically_valid_candidate.epistemic", "S04.revision_bound_conflict.settled_winner",
                          "S05.owner_A_queries_B.titles", "S06.index20_canonical22.revoked_hit_returned",
                          "S07.full_fetch.utf8_bytes", "S08.extractor_quota_exhausted.paid_fallback_calls",
                          "S09.same_owner_fresh_session.external_action_replays", "S10.intent_durable_copy_cleanup_pending.erasure_complete",
                          "S11.unreviewed_draft.result", "S12.canonical_status_revoked_under_pressure.retained_body")
        for path in expected_paths:
            self.assertTrue(any(path in error for error in result["errors"]), path)

    def test_missing_trace_case_and_step_fail(self):
        self.correct["cases"].pop()
        self.assertFalse(check_traces(self.scenarios, self.correct)["valid"])
        self.setUp()
        self.correct["cases"][0]["steps"].pop()
        self.assertFalse(check_traces(self.scenarios, self.correct)["valid"])

    def test_duplicate_case_and_step_ids_fail(self):
        self.correct["cases"].append(copy.deepcopy(self.correct["cases"][0]))
        self.assertFalse(check_traces(self.scenarios, self.correct)["valid"])
        self.setUp()
        self.correct["cases"][0]["steps"].append(copy.deepcopy(self.correct["cases"][0]["steps"][0]))
        self.assertFalse(check_traces(self.scenarios, self.correct)["valid"])

    def test_bool_is_not_integer(self):
        self.correct["cases"][0]["steps"][2]["observed"]["new_records"] = False
        result = check_traces(self.scenarios, self.correct)
        self.assertFalse(result["valid"])
        self.assertTrue(any("expected type int" in error for error in result["errors"]))

    def test_extra_metadata_is_a_failure(self):
        self.correct["cases"][4]["steps"][0]["observed"]["hidden_owner_count"] = 1
        result = check_traces(self.scenarios, self.correct)
        self.assertFalse(result["valid"])
        self.assertTrue(any("unexpected observable" in error for error in result["errors"]))

    def test_wrong_provenance_revision_fails(self):
        self.correct["cases"][6]["steps"][0]["observed"]["provenance"][0]["revision"] = "r16"
        result = check_traces(self.scenarios, self.correct)
        self.assertFalse(result["valid"])
        self.assertTrue(any("provenance[0].revision" in error for error in result["errors"]))

    def test_synthetic_label_required(self):
        self.correct["synthetic"] = False
        self.assertFalse(check_traces(self.scenarios, self.correct)["valid"])


if __name__ == "__main__":
    unittest.main()
