"""Independently recalculate retained ranking arithmetic using only the stdlib.

This checks successful retained runs against results/summary.json. It does not
run retrieval, import the evaluator, validate access control, or judge labels.
Run from any directory: python -I -B scripts/check_arithmetic.py --out check.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 64 * 1024 * 1024
TOLERANCE = 1e-12
QUALITY = ("recall_at_k", "precision_at_k", "mrr", "ndcg_at_k",
           "precision_at_k_oracle_ceiling")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def finite_float(value):
    number = float(value)
    require(math.isfinite(number), "overflow/non-finite JSON number")
    return number


def parse_json(data):
    require(len(data) <= LIMIT, "JSON exceeds 64 MiB limit")
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant, parse_float=finite_float)


def read_json(path):
    require(path.stat().st_size <= LIMIT, "input exceeds 64 MiB limit")
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            return parse_json(stream.read(LIMIT + 1))
    return parse_json(path.read_bytes())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def indexed(rows, key, label):
    require(isinstance(rows, list) and bool(rows), label + ": expected nonempty array")
    result = {}
    for row in rows:
        require(isinstance(row, dict), label + ": expected object")
        identifier = row.get(key)
        require(isinstance(identifier, str) and bool(identifier.strip()),
                label + ": missing identifier")
        require(identifier not in result, label + ": duplicate identifier " + identifier)
        result[identifier] = row
    return result


def ranking_values(ids, gold, k):
    """Return null quality for empty gold; use fixed k slots for precision."""
    require(type(k) is int and k > 0, "k must be a positive integer")
    require(isinstance(ids, list) and all(isinstance(x, str) for x in ids),
            "ranked IDs must be strings")
    require(len(set(ids)) == len(ids), "duplicate ranked record ID")
    require(isinstance(gold, dict) and all(type(g) is int and 1 <= g <= 3
                                         for g in gold.values()), "invalid relevance grade")
    if not gold:
        return {name: None for name in QUALITY}, 0
    selected = ids[:k]
    hits = 0
    first_hit = 0.0
    gain = 0.0
    for offset, record in enumerate(selected):
        grade = gold.get(record, 0)
        if grade:
            hits += 1
            if first_hit == 0:
                first_hit = 1.0 / (offset + 1)
            gain += (2.0 ** grade - 1.0) / math.log2(offset + 2)
    ideal = 0.0
    for offset, grade in enumerate(sorted(gold.values(), reverse=True)[:k]):
        ideal += (2.0 ** grade - 1.0) / math.log2(offset + 2)
    return {"recall_at_k": hits / len(gold), "precision_at_k": hits / k,
            "mrr": first_hit, "ndcg_at_k": gain / ideal,
            "precision_at_k_oracle_ceiling": min(len(gold), k) / k}, hits


def summarize(rows):
    positive = [r for r in rows if r["answerable"]]
    negative = [r for r in rows if not r["answerable"]]
    result = {"query_count": len(rows), "answerable_queries": len(positive),
              "unanswerable_queries": len(negative), "ok_queries": len(rows),
              "unavailable_queries": 0, "error_queries": 0}
    for name in QUALITY:
        result[name] = (math.fsum(r["metrics"][name] for r in positive) / len(positive)
                        if positive else None)
    empty = sum(not r["ids"] for r in negative)
    result.update({"sparse_gold_queries": sum(r["metrics"][QUALITY[-1]] < 1
                                              for r in positive),
                   "unanswerable_abstained": empty,
                   "unanswerable_false_positive_queries": len(negative) - empty,
                   "unanswerable_returned_records": sum(len(r["ids"]) for r in negative),
                   "unanswerable_abstention_rate": empty / len(negative) if negative else None})
    return result


def compare_values(actual, reference, label, differences):
    require(isinstance(reference, dict), label + ": missing reference object")
    for key, value in actual.items():
        require(key in reference, label + ": missing reference field " + key)
        other = reference[key]
        if value is None:
            require(other is None, label + "." + key + ": null mismatch")
        elif type(value) is int:
            require(type(other) is int and value == other, label + "." + key + ": count mismatch")
        else:
            require(type(other) in (int, float) and math.isfinite(other),
                    label + "." + key + ": invalid reference number")
            delta = abs(value - other)
            differences.append(delta)
            require(delta <= TOLERANCE, label + "." + key + ": arithmetic mismatch")


def self_checks():
    """Literal small examples and deliberately invalid inputs, not benchmark data."""
    names = []
    actual, hits = ranking_values(["x", "a", "b"], {"a": 3, "b": 1}, 3)
    expected = {"recall_at_k": 1.0, "precision_at_k": 2 / 3, "mrr": 0.5,
                "ndcg_at_k": (7 / math.log2(3) + 1 / 2) / (7 + 1 / math.log2(3)),
                "precision_at_k_oracle_ceiling": 2 / 3}
    compare_values(actual, expected, "graded hand calculation", [])
    require(hits == 2, "hand calculation hit count")
    names.append("graded-ranking-hand-calculation")
    actual, hits = ranking_values([], {"a": 3}, 10)
    require(hits == 0 and all(actual[n] == 0 for n in QUALITY[:-1])
            and actual[QUALITY[-1]] == 0.1, "empty ranking calculation")
    names.append("empty-ranking-zero-quality-fixed-ceiling")
    actual, hits = ranking_values(["a"], {"a": 1}, 10)
    require(actual["precision_at_k"] == 0.1 and actual["recall_at_k"] == 1,
            "fixed ten-slot precision calculation")
    names.append("unfilled-slots-count-in-precision")
    actual, hits = ranking_values(["x", "a"], {"a": 3}, 1)
    require(hits == 0 and actual["mrr"] == 0, "cutoff calculation")
    names.append("cutoff-excludes-later-hit")
    actual, hits = ranking_values(["x"], {}, 10)
    require(hits == 0 and all(v is None for v in actual.values()), "empty gold calculation")
    negative = [{"answerable": False, "ids": [], "metrics": actual},
                {"answerable": False, "ids": ["x"], "metrics": actual}]
    aggregate = summarize(negative)
    require(aggregate["unanswerable_abstention_rate"] == 0.5
            and aggregate["unanswerable_returned_records"] == 1
            and aggregate["recall_at_k"] is None, "empty gold aggregation")
    names.append("empty-gold-diagnostics-excluded-from-quality")
    invalid = {
        "duplicate-ranks-rejected": lambda: ranking_values(["a", "a"], {"a": 1}, 2),
        "boolean-grade-rejected": lambda: ranking_values(["a"], {"a": True}, 1),
        "duplicate-json-key-rejected": lambda: parse_json(b'{"a":1,"a":2}'),
        "nonfinite-json-rejected": lambda: parse_json(b'{"a":NaN}'),
        "overflow-json-rejected": lambda: parse_json(b'{"a":1e999}'),
        "truncated-json-rejected": lambda: parse_json(b'{"a":'),
        "duplicate-query-id-rejected": lambda: indexed([{"id": "q"}, {"id": "q"}], "id", "query"),
        "arithmetic-mismatch-rejected": lambda: compare_values({"mrr": 0.5}, {"mrr": 1.0}, "bad", []),
    }
    for name, operation in invalid.items():
        try:
            operation()
        except ValueError:
            names.append(name)
        else:
            raise ValueError("self-check failed to reject: " + name)
    return {"passed": True, "count": len(names), "checks": names}


def check(root):
    corpus_path, query_path, summary_path = (root / p for p in
        ("fixtures/corpus.json", "fixtures/queries.json", "results/summary.json"))
    corpus, query_data, reference = (read_json(p) for p in (corpus_path, query_path, summary_path))
    require(corpus.get("schema") == "hippo-corpus/v1", "unsupported corpus schema")
    require(query_data.get("schema") == "hippo-queries/v1", "unsupported query schema")
    require(reference.get("schema") == "release-result-summary/v1", "unsupported summary schema")
    records = indexed(corpus.get("records"), "id", "records")
    queries = indexed(query_data.get("queries"), "id", "queries")
    for query in queries.values():
        gold = query.get("relevance")
        require(isinstance(gold, dict) and set(gold) <= set(records), "unknown relevance record")
        ranking_values([], gold, 1)
        require(type(query.get("answerable")) is bool and query["answerable"] == bool(gold),
                "answerability disagrees with relevance")
        require(isinstance(query.get("category"), str), "query category missing")
        require(query.get("split") in ("development", "heldout"), "unsupported query split")
    fixture_bytes = json.dumps({"corpus": corpus, "queries": query_data}, sort_keys=True,
                              ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    fixture_digest = hashlib.sha256(fixture_bytes).hexdigest()
    references = indexed(reference.get("runs"), "raw_file", "reference runs")
    results, all_differences = [], []
    for relative, retained in references.items():
        path = (root / relative).resolve()
        require(path.is_relative_to(root), "reference raw path leaves repository")
        raw_hash = sha256(path)
        require(raw_hash == retained.get("raw_sha256"), "raw file hash disagrees with reference")
        raw = read_json(path)
        require(raw.get("schema") == "hippo-eval-run/v2", "unsupported raw schema")
        require(raw.get("integrity_errors") == [], "raw bundle reports integrity errors")
        require(raw.get("identity", {}).get("fixture_digest") == fixture_digest,
                "raw bundle fixture identity mismatch")
        require(raw.get("identity") == retained.get("source_identity"), "reference identity mismatch")
        require(raw.get("configuration") == retained.get("configuration"), "reference configuration mismatch")
        split = raw.get("split")
        require(split in ("development", "heldout") and split == retained.get("split"), "split mismatch")
        expected = {key: q for key, q in queries.items() if q["split"] == split}
        k = raw["configuration"].get("k")
        require(type(k) is int and k > 0, "invalid raw k")
        analysis = retained.get("analysis", {})
        require(analysis.get("valid") is True and analysis.get("k") == k, "reference analysis invalid")
        methods = indexed(raw.get("methods"), "name", "raw methods")
        reference_methods = indexed(analysis.get("methods"), "name", "reference methods")
        require(set(methods) == set(reference_methods), "method coverage mismatch")
        run = {"raw_file": relative, "raw_sha256": raw_hash, "split": split,
               "run_id": raw.get("run_id"), "fixture_digest": fixture_digest,
               "recorded_source_digest": raw["identity"]["source_digest"],
               "recorded_configuration_digest": raw.get("configuration_digest"), "k": k, "methods": []}
        for name, method in methods.items():
            require(method.get("status") == "EXECUTED" and method.get("errors") == [],
                    "this arithmetic checker requires executed error-free methods")
            observed = indexed(method.get("queries"), "query_id", "observed queries")
            require(set(observed) == set(expected), "query coverage mismatch")
            ref_method = reference_methods[name]
            require(ref_method.get("valid") is True, "reference method invalid")
            ref_queries = indexed(ref_method.get("queries"), "query_id", "reference queries")
            require(set(ref_queries) == set(expected), "reference query coverage mismatch")
            rows, differences = [], []
            for query_id, observation in observed.items():
                require(observation.get("status") == "OK" and observation.get("errors") == [],
                        "this arithmetic checker requires OK error-free query observations")
                ranks = observation.get("ranked")
                require(isinstance(ranks, list) and len(ranks) <= k, "malformed or overlong ranked list")
                ids = []
                for rank in ranks:
                    require(isinstance(rank, dict), "rank must be an object")
                    identifier, score = rank.get("record_id"), rank.get("score")
                    require(isinstance(identifier, str) and identifier in records, "unknown ranked record")
                    require(type(score) in (int, float) and math.isfinite(score), "invalid rank score")
                    ids.append(identifier)
                query = expected[query_id]
                values, hits = ranking_values(ids, query["relevance"], k)
                ref_query = ref_queries[query_id]
                require(ref_query.get("ranked_ids") == ids and ref_query.get("relevance") == query["relevance"]
                        and ref_query.get("answerable") is query["answerable"], "reference query inputs mismatch")
                if query["answerable"]:
                    compare_values(values, ref_query.get("metrics"), name + "/" + query_id, differences)
                rows.append({"answerable": query["answerable"], "ids": ids, "metrics": values,
                             "hits": hits, "gold_count": len(query["relevance"]), "category": query["category"]})
            aggregate = summarize(rows)
            compare_values(aggregate, ref_method.get("summary"), name + "/summary", differences)
            for category in {row["category"] for row in rows}:
                subset = [row for row in rows if row["category"] == category]
                compare_values(summarize(subset), ref_method.get("categories", {}).get(category),
                               name + "/category/" + category, differences)
            run["methods"].append({"name": name, "summary": aggregate,
                "query_record_label_hits": sum(row["hits"] for row in rows),
                "query_record_label_total": sum(row["gold_count"] for row in rows),
                "numeric_comparisons": len(differences), "max_absolute_error": max(differences, default=0.0)})
            all_differences.extend(differences)
        results.append(run)
    return {"inputs": {str(p.relative_to(root)).replace("\\", "/"): sha256(p)
                       for p in (corpus_path, query_path, summary_path)},
            "runs": results, "numeric_comparisons": len(all_differences),
            "max_absolute_error": max(all_differences, default=0.0)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="new receipt path (existing files are protected)")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("receipt already exists; choose a new path")
    receipt = {"schema": "independent-ranking-arithmetic/v1",
               "created_at": datetime.now(timezone.utc).isoformat(), "passed": False,
               "scope": "Arithmetic-only recalculation from retained raw ranks and fixture labels; no retrieval execution.",
               "limitations": ["Not a label-validity, runtime, access-control, or full result-contract qualification.",
                               "Separately implemented formulas; same project and model-assisted authorship.",
                               "Supports completed successful runs; refuses unavailable or failed observations."],
               "checker_file": "scripts/check_arithmetic.py", "checker_sha256": sha256(Path(__file__)),
               "python_version": sys.version.split()[0], "absolute_tolerance": TOLERANCE}
    try:
        receipt["self_checks"] = self_checks()
        receipt.update(check(ROOT))
        receipt["passed"] = True
    except (ValueError, OSError, KeyError, TypeError, OverflowError, RecursionError) as exc:
        receipt["error"] = type(exc).__name__ + ": " + str(exc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print("Arithmetic check", "PASS" if receipt["passed"] else "FAIL")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
