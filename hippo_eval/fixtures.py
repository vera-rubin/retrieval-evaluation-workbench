"""Audit synthetic fixtures without inspecting retrieval output or changing labels."""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from statistics import median
from typing import Any

from .contracts import CORPUS_SCHEMA, QUERY_SCHEMA, body_digest, digest, eligible

STATUSES = {"current", "superseded", "disputed", "revoked", "deleted"}
EPISTEMICS = {"claimed", "supported", "verified"}
SPLITS = {"development", "heldout"}
RULE_NAMES = {"projects", "owners", "tasks", "statuses", "epistemics", "revisions", "require_evidence"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def validate_fixtures(corpus: Any, queries: Any) -> dict:
    """Return deterministic errors, warnings and coverage; never repair fixture data.

    This validates internal consistency, not truth or completeness of synthetic
    relevance judgments. Family separation detects declared and exact-text split
    leakage; token overlap is advisory and does not establish independence.
    """
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {}

    def error(where: str, message: str) -> None:
        errors.append(f"{where}: {message}")

    def envelope(value: Any, schema: str, field: str) -> list:
        if not isinstance(value, dict):
            error(field, "document must be an object")
            return []
        if value.get("schema") != schema:
            error(field, f"schema must be {schema}")
        if not _text(value.get("version")):
            error(field, "version must be a nonempty string")
        if not isinstance(value.get("authorship"), dict) or not value["authorship"]:
            error(field, "authorship must be a nonempty object")
        if not isinstance(value.get(field), list):
            error(field, "must be an array")
            return []
        if not value[field]:
            error(field, "must not be empty")
        return value[field]

    records = envelope(corpus, CORPUS_SCHEMA, "records")
    query_list = envelope(queries, QUERY_SCHEMA, "queries")
    by_id: dict[str, dict] = {}
    valid_records: set[str] = set()
    source_availability: dict[tuple[str, str], str] = {}
    record_families: set[str] = set()
    for index, record in enumerate(records):
        where = f"record[{index}]"
        before = len(errors)
        if not isinstance(record, dict):
            error(where, "must be an object")
            continue
        rid = record.get("id")
        if _text(rid):
            where = f"record {rid}"
            if rid in by_id:
                error(where, "duplicate record ID")
            else:
                by_id[rid] = record
        for name in ("id", "family", "project", "task", "owner", "kind", "revision", "title"):
            if not _text(record.get(name)):
                error(where, f"{name} must be a nonempty string")
        if _text(record.get("family")):
            record_families.add(record["family"])
        if type(record.get("level")) is not int or record["level"] not in (1, 2, 3):
            error(where, "level must be integer 1, 2 or 3")
        if not isinstance(record.get("status"), str) or record["status"] not in STATUSES:
            error(where, "invalid status")
        if not isinstance(record.get("epistemic"), str) or record["epistemic"] not in EPISTEMICS:
            error(where, "invalid epistemic value")
        if record.get("level") == 3 and record.get("epistemic") != "verified":
            error(where, "level 3 shared memory requires verified epistemic state")
        if "body" not in record or (record["body"] is not None and not isinstance(record["body"], str)):
            error(where, "body must be a string or null")
        else:
            if "body_sha256" not in record or record["body_sha256"] != body_digest(record["body"]):
                error(where, "body_sha256 does not match exact UTF-8 body")
            if record.get("status") == "deleted" and record["body"] is not None:
                error(where, "deleted record must have a null payload")
            if record["body"] is None and record.get("status") != "deleted":
                error(where, "null payload requires deleted status")
        provenance = record.get("provenance")
        if not isinstance(provenance, list):
            error(where, "provenance must be an array")
        else:
            seen_sources = set()
            for pindex, source in enumerate(provenance):
                pwhere = f"{where} provenance[{pindex}]"
                if not isinstance(source, dict):
                    error(pwhere, "must be an object")
                    continue
                if not _text(source.get("source_id")) or not _text(source.get("revision")):
                    error(pwhere, "source_id and revision must be nonempty strings")
                    continue
                availability = source.get("availability")
                if not isinstance(availability, str) or availability not in {"retained", "missing"}:
                    error(pwhere, "invalid availability")
                    continue
                identity = (source["source_id"], source["revision"])
                if identity in seen_sources:
                    error(pwhere, "duplicate provenance reference")
                seen_sources.add(identity)
                if identity in source_availability and source_availability[identity] != availability:
                    error(pwhere, "contradictory availability for the same source revision")
                source_availability[identity] = availability
        supersedes = record.get("supersedes")
        if not isinstance(supersedes, list) or any(not _text(item) for item in supersedes):
            error(where, "supersedes must be an array of nonempty record IDs")
        elif len(supersedes) != len(set(supersedes)):
            error(where, "duplicate supersedes reference")
        if len(errors) == before and _text(rid):
            valid_records.add(rid)

    graph: dict[str, list[str]] = {}
    for rid, record in by_id.items():
        refs = record.get("supersedes")
        if not isinstance(refs, list) or any(not _text(item) for item in refs):
            continue
        graph[rid] = refs
        for target in refs:
            if target == rid:
                error(f"record {rid}", "self supersession")
            elif target not in by_id:
                error(f"record {rid}", f"broken supersedes reference {target}")
            else:
                old = by_id[target]
                if old.get("family") != record.get("family") or old.get("project") != record.get("project"):
                    error(f"record {rid}", f"supersedes crosses family/project boundary: {target}")
                if old.get("status") == "current":
                    error(f"record {rid}", f"superseded target is still current: {target}")
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(rid: str) -> None:
        if rid in visiting:
            error(f"record {rid}", "supersession cycle")
            return
        if rid in visited:
            return
        visiting.add(rid)
        for target in graph.get(rid, []):
            if target in graph:
                visit(target)
        visiting.remove(rid)
        visited.add(rid)

    for rid in graph:
        visit(rid)

    families: dict[str, set[str]] = defaultdict(set)
    query_ids: set[str] = set()
    exact_queries: dict[tuple[str, str], dict] = {}
    split_texts: dict[str, set[str]] = defaultdict(set)
    for index, query in enumerate(query_list):
        where = f"query[{index}]"
        if not isinstance(query, dict):
            error(where, "must be an object")
            continue
        qid = query.get("id")
        if _text(qid):
            where = f"query {qid}"
            if qid in query_ids:
                error(where, "duplicate query ID")
            query_ids.add(qid)
        for name in ("id", "family", "category", "text", "rationale"):
            if not _text(query.get(name)):
                error(where, f"{name} must be a nonempty string")
        if isinstance(query.get("text"), str):
            for rid in by_id:
                if rid in query["text"]:
                    error(where, f"oracle record ID embedded in query text: {rid}")
        split = query.get("split")
        if not isinstance(split, str) or split not in SPLITS:
            error(where, "invalid split")
        elif _text(query.get("family")):
            families[query["family"]].add(split)
            if _text(query.get("text")):
                split_texts[_normalized(query["text"])].add(split)
        if _text(query.get("family")) and query["family"] not in record_families:
            error(where, "family has no corpus records")
        relevance = query.get("relevance")
        if not isinstance(relevance, dict):
            error(where, "relevance must be an object")
            relevance = {}
        if type(query.get("answerable")) is not bool or query.get("answerable") != bool(relevance):
            error(where, "answerable must equal whether relevance is nonempty")
        rules = query.get("rules")
        rules_ok = isinstance(rules, dict)
        if not rules_ok:
            error(where, "rules must be an object")
        else:
            if set(rules) != RULE_NAMES:
                error(where, "rules must contain exactly the declared rule fields")
                rules_ok = False
            for name in sorted(RULE_NAMES - {"require_evidence"}):
                value = rules.get(name)
                if name in {"tasks", "revisions"} and value is None:
                    continue
                if not isinstance(value, list) or any(not _text(item) for item in value):
                    error(where, f"rules.{name} must be an array of nonempty strings")
                    rules_ok = False
                else:
                    if len(value) != len(set(value)):
                        error(where, f"rules.{name} has duplicate values")
                        rules_ok = False
                    allowed = STATUSES if name == "statuses" else EPISTEMICS if name == "epistemics" else None
                    if allowed is not None and any(item not in allowed for item in value):
                        error(where, f"rules.{name} contains invalid enum values")
                        rules_ok = False
            if type(rules.get("require_evidence")) is not bool:
                error(where, "rules.require_evidence must be boolean")
                rules_ok = False
        for rid, grade in relevance.items():
            if type(grade) is not int or grade not in (1, 2, 3):
                error(where, f"relevance grade for {rid} must be integer 1, 2 or 3")
            if rid not in by_id:
                error(where, f"broken relevant record reference {rid}")
            elif rules_ok and rid in valid_records:
                if not eligible(by_id[rid], query):
                    error(where, f"relevant record is ineligible: {rid}")
                if by_id[rid]["family"] != query.get("family"):
                    error(where, f"relevant record crosses family boundary: {rid}")
        if rules_ok and _text(query.get("text")):
            identity = (_normalized(query["text"]), digest(rules))
            if identity in exact_queries:
                earlier = exact_queries[identity]
                kind = "contradictory labels" if earlier.get("relevance") != relevance else "duplicate query text and rules"
                error(where, f"{kind}; also used by {earlier.get('id')}")
            else:
                exact_queries[identity] = query

    for family, splits in sorted(families.items()):
        if len(splits) > 1:
            error(f"family {family}", "development/heldout split leakage")
    for text, splits in split_texts.items():
        if len(splits) > 1:
            error("queries", f"exact query text crosses splits: {text[:90]}")
    for family in sorted(record_families - set(families)):
        warnings.append(f"family {family}: records have no queries")

    search_texts: dict[str, list[dict]] = defaultdict(list)
    for rid, record in by_id.items():
        if not isinstance(record.get("title"), str) or (record.get("body") is not None and not isinstance(record.get("body"), str)):
            continue
        text = record["title"] + "\n" + (record.get("body") or "")
        for other_id in by_id:
            if other_id in text:
                error(f"record {rid}", f"oracle record ID embedded in searchable text: {other_id}")
        if record.get("body") is not None:
            search_texts[_normalized(text)].append(record)
    for group in search_texts.values():
        if len(group) < 2:
            continue
        ids = ", ".join(record["id"] for record in group)
        group_splits = set().union(*(families.get(record.get("family"), set()) for record in group))
        if len(group_splits) > 1:
            error("records", f"identical searchable text crosses splits: {ids}")
        else:
            warnings.append(f"records: identical searchable text (review scope/duplication): {ids}")

    # Advisory token-overlap audit catches obvious family copies, not semantic leakage.
    tokens = []
    for rid, record in by_id.items():
        if not isinstance(record.get("body"), str):
            continue
        words = set(re.findall(r"\w+", record["body"].casefold()))
        if len(words) >= 20:
            tokens.append((rid, record.get("family"), words))
    for index, (rid, family, words) in enumerate(tokens):
        splits = families.get(family, set())
        for other_id, other_family, other_words in tokens[index + 1:]:
            other_splits = families.get(other_family, set())
            if splits and other_splits and splits.isdisjoint(other_splits):
                if len(words & other_words) / len(words | other_words) >= 0.85:
                    warnings.append(f"records: near-duplicate text across splits: {rid}, {other_id}")

    good_records = [record for record in records if isinstance(record, dict)]
    good_queries = [query for query in query_list if isinstance(query, dict)]
    def counts(values: list[Any]) -> dict:
        return dict(sorted(Counter(str(value) for value in values).items()))
    summary.update({
        "record_count": len(records), "query_count": len(query_list),
        "family_count": len(record_families),
        "queries_by_split": counts([query.get("split") for query in good_queries]),
        "queries_by_category": counts([query.get("category") for query in good_queries]),
        "records_by_status": counts([record.get("status") for record in good_records]),
        "records_by_epistemic": counts([record.get("epistemic") for record in good_records]),
        "records_by_level": counts([record.get("level") for record in good_records]),
        "families_by_split": {split: sorted(family for family, values in families.items() if split in values) for split in sorted(SPLITS)},
        "unanswerable_count": sum(query.get("answerable") is False for query in good_queries),
        "multi_record_query_count": sum(isinstance(query.get("relevance"), dict) and len(query["relevance"]) > 1 for query in good_queries),
        "deleted_payload_count": sum(record.get("body") is None for record in good_records),
        "long_body_count_1000_chars": sum(isinstance(record.get("body"), str) and len(record["body"]) > 1000 for record in good_records),
        "label_validation": "internal consistency only; synthetic judgments are not human validated",
    })
    pool_sizes = []
    for query in good_queries:
        try:
            size = sum(eligible(by_id[rid], query) for rid in valid_records)
        except (KeyError, TypeError):
            continue
        pool_sizes.append({"query_id": query.get("id"), "split": query.get("split"),
                           "category": query.get("category"), "answerable": query.get("answerable"),
                           "eligible_count": size, "relevant_count": len(query.get("relevance", {})) if isinstance(query.get("relevance"), dict) else 0})
    answerable_pools = [item for item in pool_sizes if item["answerable"] is True]
    summary["eligible_pools"] = {
        "min": min((item["eligible_count"] for item in pool_sizes), default=0),
        "median": median([item["eligible_count"] for item in pool_sizes]) if pool_sizes else 0,
        "max": max((item["eligible_count"] for item in pool_sizes), default=0),
        "answerable_at_most_10": sum(item["eligible_count"] <= 10 for item in answerable_pools),
        "answerable_total": len(answerable_pools),
        "answerable_at_most_10_by_split": counts([item["split"] for item in answerable_pools if item["eligible_count"] <= 10]),
        "answerable_at_most_10_by_category": counts([item["category"] for item in answerable_pools if item["eligible_count"] <= 10]),
        "per_query": pool_sizes,
    }
    return {"valid": not errors, "errors": errors, "warnings": warnings, "summary": summary}
