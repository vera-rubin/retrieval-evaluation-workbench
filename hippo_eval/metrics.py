"""Strict scoring of observed synthetic retrieval, never product assurance.

Malformed observations invalidate quality aggregates instead of disappearing
from denominators. Explicit unavailable/error responses remain visible and
score as empty retrieval for end-to-end quality on executed methods.
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Any

from .contracts import METRIC_VERSION, RUN_SCHEMA, body_digest, digest, eligible

ANALYSIS_SCHEMA = "hippo-eval-analysis/v1"
COMPARISON_SCHEMA = "hippo-eval-comparison/v1"
OBSERVED_FIELDS = ("project", "task", "owner", "status", "epistemic", "revision")
QUALITY_FIELDS = ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k")


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _json_digest(value: Any, errors: list[str], path: str) -> str | None:
    try:
        return digest(value)
    except (TypeError, ValueError, OverflowError, RecursionError):
        errors.append(f"{path}: must be finite JSON data")
        return None


def _latency(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None}
    ordered = sorted(values)
    return {"count": len(values), "mean_ms": statistics.fmean(values),
            "p50_ms": statistics.median(values),
            "p95_ms": ordered[math.ceil(len(ordered) * .95) - 1], "max_ms": ordered[-1]}


def _ranking_scores(ids: list[str], relevance: dict[str, int], k: int) -> dict:
    """Precision uses k slots, including unfilled slots; relevance is binary for R/P/MRR."""
    selected = ids[:k]
    hits = sum(record_id in relevance for record_id in selected)
    reciprocal = next((1 / rank for rank, record_id in enumerate(selected, 1)
                       if record_id in relevance), 0.0)
    dcg = sum((2 ** relevance.get(record_id, 0) - 1) / math.log2(rank + 1)
              for rank, record_id in enumerate(selected, 1))
    ideal = sum((2 ** grade - 1) / math.log2(rank + 1)
                for rank, grade in enumerate(sorted(relevance.values(), reverse=True)[:k], 1))
    return {"recall_at_k": hits / len(relevance), "precision_at_k": hits / k,
            "precision_at_k_oracle_ceiling": min(k, len(relevance)) / k,
            "mrr": reciprocal, "ndcg_at_k": dcg / ideal if ideal else 0.0}


def _summarize(rows: list[dict]) -> dict:
    answerable = [row for row in rows if row["answerable"]]
    negatives = [row for row in rows if not row["answerable"]]
    summary = {"query_count": len(rows), "answerable_queries": len(answerable),
               "unanswerable_queries": len(negatives),
               "ok_queries": sum(row["status"] == "OK" for row in rows),
               "unavailable_queries": sum(row["status"] == "UNAVAILABLE" for row in rows),
               "error_queries": sum(row["status"] == "ERROR" for row in rows)}
    for key in QUALITY_FIELDS:
        summary[key] = statistics.fmean(row["metrics"][key] for row in answerable) if answerable else None
    summary["precision_at_k_oracle_ceiling"] = statistics.fmean(row["metrics"]["precision_at_k_oracle_ceiling"] for row in answerable) if answerable else None
    summary["sparse_gold_queries"] = sum(row["metrics"]["precision_at_k_oracle_ceiling"] < 1 for row in answerable)
    # A failed request is not a successful abstention.
    abstained = sum(row["status"] == "OK" and not row["ranked_ids"] for row in negatives)
    false_positive = sum(bool(row["ranked_ids"]) for row in negatives)
    summary.update({"unanswerable_abstained": abstained,
                    "unanswerable_false_positive_queries": false_positive,
                    "unanswerable_returned_records": sum(len(row["ranked_ids"]) for row in negatives),
                    "unanswerable_abstention_rate": abstained / len(negatives) if negatives else None,
                    "latency": _latency([row["elapsed_ms"] for row in rows])})
    pools = [row["eligible_record_count"] for row in rows]
    distractors = [row["eligible_distractor_count"] for row in rows]
    summary["retrieval_pool"] = {"minimum": min(pools) if pools else None, "mean": statistics.fmean(pools) if pools else None,
                                 "maximum": max(pools) if pools else None,
                                 "mean_distractors": statistics.fmean(distractors) if distractors else None}
    return summary


def _check_identity(identity: Any, errors: list[str]) -> None:
    if not isinstance(identity, dict):
        errors.append("identity: expected object")
        return
    for key in ("source_digest", "fixture_digest", "dependency_digest"):
        if not _sha(identity.get(key)):
            errors.append(f"identity.{key}: expected lowercase SHA256")
    if identity.get("metric_version") != METRIC_VERSION:
        errors.append("identity.metric_version: unsupported metric version")
    git_head = identity.get("git_head")
    archive_identity = git_head is None and identity.get("source_origin") == "source_archive"
    if not archive_identity and (not isinstance(git_head, str) or len(git_head) not in (40, 64) or any(c not in "0123456789abcdef" for c in git_head)):
        errors.append("identity.git_head: expected full lowercase commit identifier")
    sources = identity.get("source_files")
    if not isinstance(sources, dict) or not sources:
        errors.append("identity.source_files: expected nonempty relative-path to SHA256 mapping")
    else:
        for path, value in sources.items():
            if not _text(path) or path.startswith(("/", "\\")) or ":" in path or ".." in path.replace("\\", "/").split("/") or not _sha(value):
                errors.append("identity.source_files: invalid relative path or SHA256")
        if _json_digest(sources, errors, "identity.source_files") != identity.get("source_digest"):
            errors.append("identity.source_digest: does not match source_files")
    dependencies = identity.get("dependencies")
    if not isinstance(dependencies, dict) or not dependencies:
        errors.append("identity.dependencies: expected nonempty dependency version map")
    elif _json_digest(dependencies, errors, "identity.dependencies") != identity.get("dependency_digest"):
        errors.append("identity.dependency_digest: does not match dependencies")


def _check_resource(bundle: dict, config: Any, errors: list[str]) -> dict:
    start = len(errors)
    required = bundle.get("supervision_required", False)
    resource = bundle.get("resource")
    validation = {"required": required, "provided": resource is not None, "passed": False,
                  "scope": "sampled owned-process RSS/time receipt, not an OS hard limit or product proof"}
    if type(required) is not bool:
        errors.append("supervision_required: expected boolean")
    if resource is None:
        if required:
            errors.append("resource: required supervision receipt is missing")
        validation["status"] = "MISSING" if required else "NOT_PROVIDED"
        return validation
    if not isinstance(resource, dict):
        errors.append("resource: expected object")
        validation["status"] = "INVALID"
        return validation
    for key in ("peak_rss_bytes", "rss_samples", "limit_bytes", "monitored_pid"):
        if type(resource.get(key)) is not int or resource[key] <= 0:
            errors.append(f"resource.{key}: expected positive integer")
    for key in ("sample_interval_ms", "elapsed_ms"):
        if not _number(resource.get(key)) or resource[key] <= 0:
            errors.append(f"resource.{key}: expected finite positive number")
    limit = config.get("max_rss_bytes") if isinstance(config, dict) else None
    if type(limit) is not int or not 0 < limit <= 2147483648:
        errors.append("configuration.max_rss_bytes: supervised run must declare a positive limit <= 2 GiB")
    elif resource.get("limit_bytes") != limit:
        errors.append("resource.limit_bytes: differs from declared configuration limit")
    if type(resource.get("peak_rss_bytes")) is int and type(limit) is int and resource["peak_rss_bytes"] > limit:
        errors.append("resource.peak_rss_bytes: observed peak exceeds declared limit")
    if "failure" not in resource or resource["failure"] is not None:
        errors.append(f"resource.failure: guard reported failure or omitted outcome: {resource.get('failure')}")
    if type(resource.get("child_exit_code")) is not int or resource["child_exit_code"] != 0:
        errors.append("resource.child_exit_code: expected successful child exit 0")
    if resource.get("scope") != "direct_base_interpreter_owned_inference_process_only":
        errors.append("resource.scope: receipt does not identify the directly monitored owned interpreter")
    runtime = bundle.get("execution_runtime")
    if not isinstance(runtime, dict):
        errors.append("execution_runtime: missing monitored interpreter identity")
    else:
        if type(runtime.get("pid")) is not int or runtime["pid"] <= 0 or runtime["pid"] != resource.get("monitored_pid"):
            errors.append("resource.monitored_pid: does not match execution_runtime.pid")
        if runtime.get("isolated") is not True or runtime.get("no_site") is not True:
            errors.append("execution_runtime: direct interpreter must report isolated/no_site true")
        if not _text(runtime.get("executable_name")):
            errors.append("execution_runtime.executable_name: required")
    identity = bundle.get("identity")
    dependencies = identity.get("dependencies") if isinstance(identity, dict) else None
    if not isinstance(dependencies, dict) or not _sha(dependencies.get("python_executable_sha256")):
        errors.append("identity.dependencies.python_executable_sha256: supervised interpreter hash required")
    validation["passed"] = len(errors) == start
    validation["status"] = "PASSED" if validation["passed"] else "INVALID"
    return validation


def _fixtures(corpus: Any, queries: Any, split: str, errors: list[str]) -> tuple[dict, dict]:
    records: dict[str, dict] = {}
    selected: dict[str, dict] = {}
    if not isinstance(corpus, dict) or not isinstance(corpus.get("records"), list):
        errors.append("corpus.records: expected array")
        return records, selected
    for record in corpus["records"]:
        if not isinstance(record, dict) or not _text(record.get("id")):
            errors.append("corpus.records: malformed record identifier")
            continue
        record_id = record["id"]
        if record_id in records:
            errors.append(f"corpus.records: duplicate ID {record_id}")
        records[record_id] = record
        if not isinstance(record.get("body"), (str, type(None))) or body_digest(record.get("body")) != record.get("body_sha256"):
            errors.append(f"corpus.{record_id}: body digest mismatch")
        if not isinstance(record.get("provenance"), list):
            errors.append(f"corpus.{record_id}: malformed provenance")
        elif any(not isinstance(source, dict) or not _text(source.get("source_id")) or not _text(source.get("revision")) or source.get("availability") not in ("retained", "missing") for source in record["provenance"]):
            errors.append(f"corpus.{record_id}: malformed provenance entry")
    if not isinstance(queries, dict) or not isinstance(queries.get("queries"), list):
        errors.append("queries.queries: expected array")
        return records, selected
    seen: set[str] = set()
    for query in queries["queries"]:
        if not isinstance(query, dict) or not _text(query.get("id")):
            errors.append("queries.queries: malformed query identifier")
            continue
        query_id = query["id"]
        if query_id in seen:
            errors.append(f"queries.queries: duplicate ID {query_id}")
        seen.add(query_id)
        if query.get("split") != split:
            continue
        selected[query_id] = query
        if not _text(query.get("category")) or not _text(query.get("text")):
            errors.append(f"queries.{query_id}: missing category/text")
        relevance = query.get("relevance")
        if not isinstance(relevance, dict) or any(not _text(record_id) or type(grade) is not int or grade not in (1, 2, 3) for record_id, grade in relevance.items()):
            errors.append(f"queries.{query_id}: invalid relevance grades")
            continue
        if type(query.get("answerable")) is not bool or query["answerable"] != bool(relevance):
            errors.append(f"queries.{query_id}: answerable must match nonempty relevance")
        for record_id in relevance:
            try:
                allowed = record_id in records and eligible(records[record_id], query)
            except (AttributeError, KeyError, TypeError, ValueError):
                allowed = False
            if not allowed:
                errors.append(f"queries.{query_id}: relevant ID {record_id} is unknown/ineligible")
        # Validate rules even when relevance is empty.
        rules = query.get("rules")
        if not isinstance(rules, dict):
            errors.append(f"queries.{query_id}: missing rules")
        else:
            for key in ("projects", "owners", "tasks", "statuses", "epistemics", "revisions"):
                if key not in rules or not (isinstance(rules[key], list) or key in ("tasks", "revisions") and rules[key] is None):
                    errors.append(f"queries.{query_id}.rules.{key}: malformed scope rule")
            if type(rules.get("require_evidence")) is not bool:
                errors.append(f"queries.{query_id}.rules.require_evidence: expected boolean")
    if not selected:
        errors.append(f"queries: no queries in declared split {split!r}")
    return records, selected


def _check_ranked(items: list, query: dict, records: dict, k: int, errors: list[str], path: str) -> list[str]:
    ids = []
    previous_score = None
    if len(items) > k:
        errors.append(f"{path}: more than k ranked records")
    for index, item in enumerate(items):
        here = f"{path}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{here}: expected object")
            continue
        record_id = item.get("record_id")
        if not _text(record_id):
            errors.append(f"{here}.record_id: expected nonempty string")
            continue
        if record_id in ids:
            errors.append(f"{here}: duplicate record ID {record_id}")
        ids.append(record_id)
        if not _number(item.get("score")):
            errors.append(f"{here}.score: expected finite number")
        else:
            if previous_score is not None and item["score"] > previous_score:
                errors.append(f"{here}.score: ranked scores must be non-increasing for these adapters")
            previous_score = item["score"]
        record = records.get(record_id)
        if record is None:
            errors.append(f"{here}: unknown record ID {record_id}")
            continue
        try:
            allowed = eligible(record, query)
        except (AttributeError, KeyError, TypeError, ValueError):
            allowed = False
        if not allowed:
            errors.append(f"{here}: returned record violates scope/status/evidence rules")
        if "body_sha256" not in item or item["body_sha256"] != record.get("body_sha256"):
            errors.append(f"{here}.body_sha256: full fetched body differs from canonical fixture")
        if item.get("provenance_sha256") != digest(record.get("provenance")):
            errors.append(f"{here}.provenance_sha256: fetched provenance differs from canonical fixture")
        if item.get("record_sha256") != digest(record):
            errors.append(f"{here}.record_sha256: complete fetched record differs from canonical fixture")
        observed = item.get("observed")
        if not isinstance(observed, dict):
            errors.append(f"{here}.observed: missing fetched fields")
        else:
            for key in OBSERVED_FIELDS:
                if key not in observed or observed[key] != record.get(key):
                    errors.append(f"{here}.observed.{key}: fetched value differs from canonical fixture")
        fidelity = item.get("fidelity")
        if not isinstance(fidelity, dict) or fidelity.get("passed") is not True or fidelity.get("issues") != []:
            errors.append(f"{here}.fidelity: full-fetch fidelity did not pass")
        if "chunk_ids" in item and (not isinstance(item["chunk_ids"], list) or any(not _text(value) for value in item["chunk_ids"]) or len(item["chunk_ids"]) != len(set(item["chunk_ids"]))):
            errors.append(f"{here}.chunk_ids: expected unique string array")
        if "chunks" in item and not isinstance(item["chunks"], list):
            errors.append(f"{here}.chunks: expected array")
        elif "chunks" in item:
            found_chunk_ids = []
            for chunk_index, chunk in enumerate(item["chunks"]):
                chunk_path = f"{here}.chunks[{chunk_index}]"
                if not isinstance(chunk, dict):
                    errors.append(f"{chunk_path}: expected object")
                    continue
                chunk_id = chunk.get("chunk_id")
                if not _text(chunk_id) or chunk_id in found_chunk_ids:
                    errors.append(f"{chunk_path}: missing/duplicate chunk ID")
                found_chunk_ids.append(chunk_id)
                field = chunk.get("field")
                source = record.get(field) if field in ("title", "body") else None
                start, end = chunk.get("char_start"), chunk.get("char_end")
                if chunk.get("record_id") != record_id:
                    errors.append(f"{chunk_path}.record_id: chunk belongs to another record")
                if not isinstance(source, str) or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source):
                    errors.append(f"{chunk_path}: invalid field/Unicode character bounds")
                    continue
                expected_text = source[start:end]
                if chunk.get("text") != expected_text or chunk.get("text_sha256") != body_digest(expected_text):
                    errors.append(f"{chunk_path}: text/hash does not match exact source substring")
                if chunk.get("source_field_sha256") != body_digest(source):
                    errors.append(f"{chunk_path}: source field hash mismatch")
                if type(chunk.get("byte_start")) is not int or type(chunk.get("byte_end")) is not int or chunk.get("byte_start") != len(source[:start].encode("utf-8")) or chunk.get("byte_end") != len(source[:end].encode("utf-8")):
                    errors.append(f"{chunk_path}: UTF-8 byte offsets mismatch")
                if type(chunk.get("token_count")) is not int or chunk["token_count"] <= 0:
                    errors.append(f"{chunk_path}.token_count: expected positive integer")
            if item.get("chunk_ids") != found_chunk_ids:
                errors.append(f"{here}: chunk_ids must agree with chunks in order")
    return ids


def score_bundle(bundle: Any, corpus: Any, queries: Any) -> dict:
    """Validate and score a run; return diagnostics rather than trusting its flags."""
    errors: list[str] = []
    result = {"schema": ANALYSIS_SCHEMA, "valid": False, "errors": errors, "warnings": [],
              "metric_version": METRIC_VERSION, "methods": [],
              "execution_scope": "executed_local_synthetic; authenticated identity, persistence and live recovery NOT RUN",
              "metric_definitions": {"k": "configuration.k", "precision_denominator": "k including unfilled slots",
                  "mrr": "reciprocal rank of first relevant result within k", "ndcg_gain": "2**grade-1",
                  "aggregation": "macro mean over answerable queries; unavailable/error = empty retrieval",
                  "unanswerable": "reported separately; request failure is not successful abstention"}}
    if not isinstance(bundle, dict):
        errors.append("bundle: expected object")
        return result
    for key in ("run_id", "split", "identity", "configuration", "configuration_digest", "created_at"):
        result[key] = bundle.get(key)
    if bundle.get("schema") != RUN_SCHEMA:
        errors.append("bundle.schema: unsupported schema")
    if bundle.get("execution") != "executed_local_synthetic":
        errors.append("bundle.execution: must be executed_local_synthetic")
    if not _text(bundle.get("run_id")):
        errors.append("bundle.run_id: required")
    try:
        parsed_time = datetime.fromisoformat(bundle.get("created_at", "").replace("Z", "+00:00"))
        if parsed_time.tzinfo is None:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        errors.append("bundle.created_at: expected timezone-aware ISO timestamp")
    if bundle.get("split") not in ("development", "heldout"):
        errors.append("bundle.split: unsupported split")
    integrity = bundle.get("integrity_errors", [])
    if not isinstance(integrity, list):
        errors.append("bundle.integrity_errors: expected array")
    elif integrity:
        errors.extend(f"bundle.integrity: {entry}" for entry in integrity)
    _check_identity(bundle.get("identity"), errors)
    fixture_hash = _json_digest({"corpus": corpus, "queries": queries}, errors, "fixtures")
    if not isinstance(bundle.get("identity"), dict) or bundle["identity"].get("fixture_digest") != fixture_hash:
        errors.append("identity.fixture_digest: does not match supplied complete fixtures")
    config = bundle.get("configuration")
    k = config.get("k") if isinstance(config, dict) else None
    result["k"] = k
    if type(k) is not int or k <= 0:
        errors.append("configuration.k: expected positive integer")
    config_hash = _json_digest(config, errors, "configuration")
    if not isinstance(config, dict) or not _sha(bundle.get("configuration_digest")) or config_hash != bundle.get("configuration_digest"):
        errors.append("configuration_digest: does not match configuration")
    result["resource_validation"] = _check_resource(bundle, config, errors)
    result["resource"] = bundle.get("resource")
    result["execution_runtime"] = bundle.get("execution_runtime")
    result["supervision_required"] = bundle.get("supervision_required", False)
    records, selected = _fixtures(corpus, queries, bundle.get("split"), errors)
    result["query_ids"] = sorted(selected)
    methods = bundle.get("methods")
    if not isinstance(methods, list) or not methods:
        errors.append("methods: expected nonempty array")
        return result
    names: set[str] = set()
    for method in methods:
        if not isinstance(method, dict) or not _text(method.get("name")):
            errors.append("methods: malformed method/name")
            continue
        name = method["name"]
        if name in names:
            errors.append(f"methods: duplicate method name {name}")
        names.add(name)
    global_valid = not errors
    for method in methods:
        if not isinstance(method, dict) or not _text(method.get("name")):
            continue
        name = method["name"]
        issues: list[str] = []
        output = {"name": name, "status": method.get("status"), "identity": method.get("identity"),
                  "configuration_digest": method.get("configuration_digest"), "valid": False,
                  "errors": issues, "reported_errors": method.get("errors"), "summary": None,
                  "categories": {}, "queries": [], "measurements": method.get("measurements")}
        result["methods"].append(output)
        status = method.get("status")
        if status not in ("EXECUTED", "NOT_RUN", "FAILED"):
            issues.append("status: unsupported method status")
        if method.get("configuration_digest") != bundle.get("configuration_digest"):
            issues.append("configuration_digest: mixed configuration identity")
        if not isinstance(method.get("identity"), dict) or not method["identity"]:
            issues.append("identity: expected nonempty method identity")
        else:
            _json_digest(method["identity"], issues, "identity")
        if not isinstance(method.get("errors"), list):
            issues.append("errors: expected array")
        elif any(not _text(error) for error in method["errors"]):
            issues.append("errors: expected nonempty diagnostic strings")
        elif status in ("FAILED", "NOT_RUN") and not method["errors"]:
            issues.append("errors: failed/not-run method requires a reason")
        elif status == "EXECUTED" and method["errors"]:
            issues.append("errors: EXECUTED method cannot contain reported method failures")
        observations = method.get("queries")
        if not isinstance(observations, list):
            issues.append("queries: expected array")
            observations = []
        if status == "NOT_RUN" and observations:
            issues.append("queries: NOT_RUN cannot contain executed observations")
        measurements = method.get("measurements")
        if not isinstance(measurements, dict):
            issues.append("measurements: expected object")
            measurements = {}
        if status == "EXECUTED":
            for key in ("load_ms", "index_ms"):
                if not _number(measurements.get(key)) or measurements[key] < 0:
                    issues.append(f"measurements.{key}: expected finite nonnegative number")
        if status == "NOT_RUN":
            for key in ("load_ms", "index_ms"):
                if key not in measurements or measurements[key] is not None:
                    issues.append(f"measurements.{key}: NOT_RUN requires explicit null")
        if "peak_rss_bytes" in measurements and measurements["peak_rss_bytes"] is not None and (type(measurements["peak_rss_bytes"]) is not int or measurements["peak_rss_bytes"] < 0):
            issues.append("measurements.peak_rss_bytes: expected nonnegative integer or null")
        if "supervisor_peak_rss_bytes" in measurements and (not isinstance(bundle.get("resource"), dict) or measurements["supervisor_peak_rss_bytes"] != bundle["resource"].get("peak_rss_bytes")):
            issues.append("measurements.supervisor_peak_rss_bytes: differs from resource receipt")
        latencies = measurements.get("query_latency_ms", [])
        if not isinstance(latencies, list) or any(not _number(value) or value < 0 for value in latencies):
            issues.append("measurements.query_latency_ms: expected finite nonnegative array")
            latencies = []
        if status == "EXECUTED" and len(latencies) != len(observations):
            issues.append("measurements.query_latency_ms: count differs from observations")
        seen: set[str] = set()
        for index, observation in enumerate(observations):
            path = f"queries[{index}]"
            row_errors: list[str] = []
            if not isinstance(observation, dict) or not _text(observation.get("query_id")):
                issues.append(f"{path}: malformed query observation")
                continue
            query_id = observation["query_id"]
            if query_id in seen:
                row_errors.append("duplicate query ID")
            seen.add(query_id)
            query = selected.get(query_id)
            if query is None:
                issues.append(f"{path}: unknown/wrong-split query ID {query_id}")
                continue
            query_status = observation.get("status")
            if query_status not in ("OK", "UNAVAILABLE", "ERROR"):
                row_errors.append("unsupported query status")
            observation_errors = observation.get("errors")
            if not isinstance(observation_errors, list):
                row_errors.append("errors must be an array")
            elif any(not _text(error) for error in observation_errors):
                row_errors.append("errors must contain nonempty diagnostic strings")
            elif query_status in ("ERROR", "UNAVAILABLE") and not observation_errors:
                row_errors.append("failed/unavailable observation requires an explicit reason")
            elif query_status == "OK" and observation_errors:
                row_errors.append("OK observation cannot contain reported errors")
            elapsed = observation.get("elapsed_ms")
            if not _number(elapsed) or elapsed < 0:
                row_errors.append("elapsed_ms must be finite/nonnegative")
            elif index < len(latencies) and elapsed != latencies[index]:
                row_errors.append("elapsed_ms differs from measurement list")
            ranked = observation.get("ranked")
            if not isinstance(ranked, list):
                row_errors.append("ranked must be an array (including valid empty results)")
                ranked = []
            if query_status in ("ERROR", "UNAVAILABLE") and ranked:
                row_errors.append("failed/unavailable observation cannot contain ranked results")
            ids = _check_ranked(ranked, query, records, k, row_errors, "ranked") if global_valid else []
            eligible_ids = {record_id for record_id, record in records.items() if eligible(record, query)} if global_valid else set()
            relevance = query.get("relevance") if isinstance(query.get("relevance"), dict) else {}
            diagnostic_counts = {"full_fetch_checks": sum(isinstance(item, dict) and _text(item.get("record_id")) and item["record_id"] in records for item in ranked) if global_valid else 0,
                                 "body_mismatches": sum(".body_sha256" in error for error in row_errors),
                                 "provenance_mismatches": sum(".provenance_sha256" in error for error in row_errors),
                                 "complete_record_mismatches": sum(".record_sha256" in error for error in row_errors),
                                 "fidelity_failures": sum(".fidelity" in error for error in row_errors),
                                 "scope_rule_violations": sum("violates scope/status/evidence" in error for error in row_errors),
                                 "observed_status_mismatches": sum(".observed.status" in error for error in row_errors),
                                 "observed_revision_mismatches": sum(".observed.revision" in error for error in row_errors),
                                 "observed_owner_mismatches": sum(".observed.owner" in error for error in row_errors)}
            row = {"query_id": query_id, "category": query.get("category"), "text": query.get("text"),
                   "rationale": query.get("rationale"), "answerable": query.get("answerable"),
                   "status": query_status, "elapsed_ms": elapsed, "ranked_ids": ids,
                   "relevance": query.get("relevance"), "metrics": None,
                   "missing_relevant_ids": sorted(set(relevance) - set(ids), key=str),
                   "eligible_record_count": len(eligible_ids),
                   "eligible_distractor_count": len(eligible_ids - set(relevance)),
                   "valid": global_valid and not row_errors, "errors": row_errors,
                   "reported_errors": observation_errors, "diagnostics": diagnostic_counts}
            if row["valid"] and row["answerable"]:
                row["metrics"] = _ranking_scores(ids, query["relevance"], k)
            output["queries"].append(row)
            issues.extend(f"{path}({query_id}): {error}" for error in row_errors)
        if status == "EXECUTED" and seen != set(selected):
            missing = sorted(set(selected) - seen)
            extra = sorted(seen - set(selected))
            issues.append(f"queries: incomplete/mixed split coverage; missing={missing}, extra={extra}")
        output["valid"] = global_valid and not issues
        output["diagnostics"] = {"contract_error_count": len(issues),
                                  "observations_received": len(observations), "observations_expected": len(selected),
                                  "invalid_queries": sum(not row["valid"] for row in output["queries"]),
                                  "query_status_counts": {value: sum(row["status"] == value for row in output["queries"])
                                                          for value in ("OK", "UNAVAILABLE", "ERROR")}}
        if output["queries"]:
            for key in output["queries"][0]["diagnostics"]:
                output["diagnostics"][key] = sum(row["diagnostics"][key] for row in output["queries"])
        if output["valid"] and status == "EXECUTED":
            output["summary"] = _summarize(output["queries"])
            for category in sorted({row["category"] for row in output["queries"]}):
                output["categories"][category] = _summarize([row for row in output["queries"] if row["category"] == category])
    result["valid"] = not errors and all(method["valid"] for method in result["methods"])
    if any(method["summary"] and method["summary"]["sparse_gold_queries"] for method in result["methods"]):
        result["warnings"].append("Sparse relevance labels cap achievable precision@k; this targeted synthetic corpus does not establish general retrieval precision. No gold labels were inflated.")
    result["diagnostics"] = {"contract_error_count": len(errors) + sum(len(method["errors"]) for method in result["methods"]),
                             "methods_executed": sum(method["status"] == "EXECUTED" for method in result["methods"]),
                             "methods_not_run": sum(method["status"] == "NOT_RUN" for method in result["methods"]),
                             "methods_failed": sum(method["status"] == "FAILED" for method in result["methods"])}
    return result


def _comparison_input_errors(value: dict) -> list[str]:
    """Reject incomplete/stale aggregates even when a caller supplies valid=true.

This is self-consistency, not authenticity. CLI callers must re-score original
observations against their bound fixtures instead of trusting embedded scores.
"""
    errors: list[str] = []
    if value.get("schema") != ANALYSIS_SCHEMA or value.get("valid") is not True or value.get("errors") != []:
        errors.append("analysis is missing, invalid, or has contract errors")
    if value.get("metric_version") != METRIC_VERSION:
        errors.append("unsupported metric version")
    _check_identity(value.get("identity"), errors)
    config = value.get("configuration")
    if not isinstance(config, dict) or type(config.get("k")) is not int or config["k"] <= 0 or value.get("k") != config["k"]:
        errors.append("missing/inconsistent configuration.k")
        return errors
    if _json_digest(config, errors, "configuration") != value.get("configuration_digest"):
        errors.append("configuration digest mismatch")
    resource_check = _check_resource(value, config, errors)
    if value.get("resource_validation") != resource_check:
        errors.append("stale/inconsistent resource validation")
    query_ids = value.get("query_ids")
    if not isinstance(query_ids, list) or not query_ids or any(not _text(query_id) for query_id in query_ids) or len(query_ids) != len(set(query_ids)):
        errors.append("missing/duplicate declared query IDs")
        return errors
    methods = value.get("methods")
    if not isinstance(methods, list):
        errors.append("missing methods")
        return errors
    for method in methods:
        if not isinstance(method, dict):
            errors.append("malformed method")
            continue
        name = method.get("name", "unknown")
        if method.get("valid") is not True or method.get("errors") != []:
            errors.append(f"{name}: invalid method")
        if method.get("configuration_digest") != value.get("configuration_digest"):
            errors.append(f"{name}: mixed configuration identity")
        if method.get("status") != "EXECUTED":
            if method.get("status") not in ("FAILED", "NOT_RUN") or method.get("summary") is not None:
                errors.append(f"{name}: non-executed method has invalid status/quality aggregate")
            continue
        rows = method.get("queries")
        if not isinstance(rows, list):
            errors.append(f"{name}: missing query rows")
            continue
        seen = set()
        row_errors = []
        for row in rows:
            if not isinstance(row, dict) or not _text(row.get("query_id")):
                row_errors.append("malformed query row")
                continue
            query_id = row["query_id"]
            if query_id in seen:
                row_errors.append("duplicate query row")
            seen.add(query_id)
            if row.get("valid") is not True or row.get("errors") != [] or type(row.get("answerable")) is not bool:
                row_errors.append(f"{query_id}: invalid query row")
                continue
            if row.get("status") not in ("OK", "UNAVAILABLE", "ERROR") or not _number(row.get("elapsed_ms")) or row["elapsed_ms"] < 0 or not _text(row.get("category")):
                row_errors.append(f"{query_id}: malformed status/latency/category")
                continue
            ids, relevance = row.get("ranked_ids"), row.get("relevance")
            if not isinstance(ids, list) or any(not _text(record_id) for record_id in ids) or len(ids) != len(set(ids)) or len(ids) > config["k"]:
                row_errors.append(f"{query_id}: malformed ranked IDs")
                continue
            if not isinstance(relevance, dict) or any(not _text(record_id) or type(grade) is not int or grade not in (1, 2, 3) for record_id, grade in relevance.items()) or row["answerable"] != bool(relevance):
                row_errors.append(f"{query_id}: malformed relevance")
                continue
            if row["status"] != "OK" and ids:
                row_errors.append(f"{query_id}: failed observation contains results")
            expected_metrics = _ranking_scores(ids, relevance, config["k"]) if relevance else None
            if row.get("metrics") != expected_metrics:
                row_errors.append(f"{query_id}: metric values differ from ranked IDs/relevance")
            if type(row.get("eligible_record_count")) is not int or type(row.get("eligible_distractor_count")) is not int or row["eligible_record_count"] < len(relevance) or row["eligible_distractor_count"] != row["eligible_record_count"] - len(relevance):
                row_errors.append(f"{query_id}: invalid eligible/distractor counts")
        if seen != set(query_ids):
            row_errors.append("truncated/mixed observed query set")
        if row_errors:
            errors.extend(f"{name}: {error}" for error in row_errors)
            continue
        expected_summary = _summarize(rows)
        if method.get("summary") != expected_summary:
            errors.append(f"{name}: stale/incomplete summary does not match query rows")
        expected_categories = {category: _summarize([row for row in rows if row["category"] == category]) for category in {row["category"] for row in rows}}
        if method.get("categories") != expected_categories:
            errors.append(f"{name}: stale/incomplete category aggregates")
    return errors


def compare_runs(before: dict, after: dict) -> dict:
    """Compare two *scored analyses*. Source changes are allowed; identities are not inferred."""
    if isinstance(before, dict) and "analysis" in before:
        before = before["analysis"]
    if isinstance(after, dict) and "analysis" in after:
        after = after["analysis"]
    reasons: list[str] = []
    comparison = {"schema": COMPARISON_SCHEMA, "compatible": False, "reasons": reasons,
                  "before_run_id": before.get("run_id") if isinstance(before, dict) else None,
                  "after_run_id": after.get("run_id") if isinstance(after, dict) else None,
                  "source_changed": None, "methods": [], "regressed": None}
    if not isinstance(before, dict) or not isinstance(after, dict):
        reasons.append("both inputs must be scored analysis objects")
        return comparison
    for label, value in (("before", before), ("after", after)):
        reasons.extend(f"{label}: {error}" for error in _comparison_input_errors(value))
    for key in ("split", "k", "metric_version", "configuration_digest"):
        if before.get(key) is None or before.get(key) != after.get(key):
            reasons.append(f"incompatible {key}")
    left_identity, right_identity = before.get("identity", {}), after.get("identity", {})
    if not isinstance(left_identity, dict) or not isinstance(right_identity, dict):
        reasons.append("missing run identity")
        left_identity, right_identity = {}, {}
    for key in ("fixture_digest", "dependency_digest", "metric_version"):
        if not left_identity.get(key) or left_identity.get(key) != right_identity.get(key):
            reasons.append(f"incompatible identity.{key}")
    comparison["source_changed"] = left_identity.get("source_digest") != right_identity.get("source_digest")
    maps = []
    for label, value in (("before", before), ("after", after)):
        methods = value.get("methods")
        mapping = {}
        if not isinstance(methods, list) or not methods:
            reasons.append(f"{label}: missing methods")
        else:
            for method in methods:
                if not isinstance(method, dict) or not _text(method.get("name")) or method["name"] in mapping:
                    reasons.append(f"{label}: malformed/duplicate method")
                    continue
                mapping[method["name"]] = method
        maps.append(mapping)
    left, right = maps
    if set(left) != set(right):
        reasons.append("incompatible method set")
    global_reasons = list(reasons)
    for name in sorted(set(left) & set(right)):
        old, new = left[name], right[name]
        method_reasons = list(global_reasons)
        for key in ("identity", "configuration_digest"):
            if not old.get(key) or old.get(key) != new.get(key):
                method_reasons.append(f"incompatible method {key}")
        if old.get("valid") is not True or new.get("valid") is not True:
            method_reasons.append("invalid method contract")
        entry = {"name": name, "compatible": not method_reasons, "reasons": method_reasons,
                 "before_status": old.get("status"), "after_status": new.get("status"),
                 "comparable": False, "deltas": {}, "categories": {}, "query_deltas": [],
                 "regressions": [], "regressed": None}
        comparison["methods"].append(entry)
        if method_reasons:
            continue
        if old.get("status") != "EXECUTED" or new.get("status") != "EXECUTED":
            entry["reasons"].append("quality not compared: one or both methods were not executed")
            continue
        if not isinstance(old.get("summary"), dict) or not isinstance(new.get("summary"), dict):
            entry["compatible"] = False
            entry["reasons"].append("missing quality aggregates")
            continue
        entry["comparable"] = True
        for key in QUALITY_FIELDS + ("unanswerable_abstention_rate",):
            a, b = old["summary"].get(key), new["summary"].get(key)
            entry["deltas"][key] = b - a if _number(a) and _number(b) else None
            if entry["deltas"][key] is not None and entry["deltas"][key] < -1e-12:
                entry["regressions"].append(key)
        for key in ("error_queries", "unavailable_queries", "unanswerable_false_positive_queries"):
            a, b = old["summary"].get(key), new["summary"].get(key)
            entry["deltas"][key] = b - a if _number(a) and _number(b) else None
            if entry["deltas"][key] is not None and entry["deltas"][key] > 0:
                entry["regressions"].append(key)
        for key in ("mean_ms", "p50_ms", "p95_ms", "max_ms"):
            a, b = old["summary"].get("latency", {}).get(key), new["summary"].get("latency", {}).get(key)
            entry["deltas"]["latency_" + key] = b - a if _number(a) and _number(b) else None
        for category in sorted(set(old.get("categories", {})) | set(new.get("categories", {}))):
            entry["categories"][category] = {}
            for key in QUALITY_FIELDS:
                a, b = old.get("categories", {}).get(category, {}).get(key), new.get("categories", {}).get(category, {}).get(key)
                delta = b - a if _number(a) and _number(b) else None
                entry["categories"][category][key] = delta
                if delta is not None and delta < -1e-12:
                    entry["regressions"].append(f"category:{category}:{key}")
        old_queries = {row["query_id"]: row for row in old.get("queries", [])}
        new_queries = {row["query_id"]: row for row in new.get("queries", [])}
        if set(old_queries) != set(new_queries):
            entry["compatible"] = False
            entry["comparable"] = False
            entry["deltas"] = {}
            entry["categories"] = {}
            entry["regressions"] = []
            entry["reasons"].append("incompatible observed query set")
            continue
        for query_id in sorted(old_queries):
            a, b = old_queries[query_id].get("metrics") or {}, new_queries[query_id].get("metrics") or {}
            entry["query_deltas"].append({"query_id": query_id, "metrics": {
                key: b[key] - a[key] if _number(a.get(key)) and _number(b.get(key)) else None for key in QUALITY_FIELDS},
                "before_status": old_queries[query_id]["status"], "after_status": new_queries[query_id]["status"]})
        entry["regressed"] = bool(entry["regressions"])
    comparison["compatible"] = not reasons and all(entry["compatible"] for entry in comparison["methods"])
    compared = [entry for entry in comparison["methods"] if entry["comparable"]]
    comparison["regressed"] = any(entry["regressed"] for entry in compared) if comparison["compatible"] and compared else None
    comparison["note"] = "Quality regressions use exact metric decreases; latency deltas are observations, not an undeclared performance gate."
    return comparison
