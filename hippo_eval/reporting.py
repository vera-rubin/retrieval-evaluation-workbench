"""Static escaped reports. No scripts, remote assets, framework, or server."""
from __future__ import annotations

import html
import json
import math
from pathlib import Path
from typing import Any

from .contracts import write_json


def _safe_json(value: Any, warnings: list[str], path: str = "$", ancestors: set | None = None) -> Any:
    """Preserve invalid-input diagnostics in valid report JSON with explicit markers."""
    ancestors = set() if ancestors is None else ancestors
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        warnings.append(f"{path}: non-finite value rendered as an INVALID marker")
        return f"INVALID_NONFINITE:{value}"
    if isinstance(value, (dict, list, tuple)):
        if id(value) in ancestors:
            warnings.append(f"{path}: cyclic input rendered as an INVALID marker")
            return "INVALID_CYCLE"
        nested = ancestors | {id(value)}
        if isinstance(value, dict):
            return {str(key): _safe_json(child, warnings, f"{path}.{key}", nested) for key, child in value.items()}
        return [_safe_json(child, warnings, f"{path}[{index}]", nested) for index, child in enumerate(value)]
    warnings.append(f"{path}: unsupported value rendered as an INVALID marker")
    return f"INVALID_TYPE:{type(value).__name__}"


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _md(value: Any) -> str:
    # Encode HTML and Markdown delimiters; every cell stays on one line.
    text = html.escape(str(value), quote=True).replace("\r", " ").replace("\n", "<br>")
    for token in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "!", "|"):
        text = text.replace(token, "\\" + token)
    return text


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _messages(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return ["INVALID diagnostics container: " + str(value)]


def _table(headers: list[str], rows: list[list[Any]]) -> tuple[str, str]:
    markdown = "| " + " | ".join(_md(value) for value in headers) + " |\n"
    markdown += "| " + " | ".join("---" for _ in headers) + " |\n"
    markdown += "".join("| " + " | ".join(_md(_fmt(value)) for value in row) + " |\n" for row in rows)
    markup = "<table><thead><tr>" + "".join(f"<th>{_h(value)}</th>" for value in headers) + "</tr></thead><tbody>"
    markup += "".join("<tr>" + "".join(f"<td>{_h(_fmt(value))}</td>" for value in row) + "</tr>" for row in rows)
    return markdown, markup + "</tbody></table>"


def write_reports(bundle: dict, analysis: dict, output_dir: str | Path, comparison: dict | None = None) -> dict:
    """Write report.json, report.md and report.html; return absolute path strings."""
    output = Path(output_dir).resolve()
    workbench = Path(__file__).resolve().parents[1]
    if not output.is_relative_to(workbench):
        raise ValueError("Reports must remain within the Retrieval-Eval workbench")
    output.mkdir(parents=True, exist_ok=True)
    serialization_warnings: list[str] = []
    run_reference = {key: bundle.get(key) for key in ("run_id", "created_at", "identity", "configuration_digest")} if isinstance(bundle, dict) else None
    payload = _safe_json({"schema": "hippo-eval-report/v1", "run_reference": run_reference,
                          "observation_note": "The original run.json is the canonical observed result bundle; this compact report does not replace it.", "analysis": analysis,
                          "comparison": comparison}, serialization_warnings)
    payload["serialization_warnings"] = serialization_warnings
    data = payload["analysis"]
    if not isinstance(data, dict):
        data = {"valid": False, "errors": ["Missing analysis object"], "methods": []}
    title = "Reproducible Retrieval Evaluation"
    scope = "Local synthetic retrieval measurements and supplied trace checks. Authenticated access control, production persistence and live recovery are outside this experiment."
    markdown = [f"# {title}\n", scope + "\n", f"Run: {_md(data.get('run_id', 'unknown'))}. Split: {_md(data.get('split', 'unknown'))}. Contract valid: {_md(data.get('valid', False))}.\n"]
    markup = [f"<h1>{_h(title)}</h1>", f"<p class=scope>{_h(scope)}</p>",
              f"<p>Run: {_h(data.get('run_id', 'unknown'))}. Split: {_h(data.get('split', 'unknown'))}. Contract valid: {_h(data.get('valid', False))}.</p>"]

    def heading(value: str, level: int = 2) -> None:
        markdown.append("#" * level + " " + _md(value) + "\n")
        markup.append(f"<h{level}>{_h(value)}</h{level}>")

    def paragraph(value: str) -> None:
        markdown.append(_md(value) + "\n")
        markup.append(f"<p>{_h(value)}</p>")

    def table(headers: list, rows: list) -> None:
        md, ht = _table(headers, rows)
        markdown.append(md)
        markup.append(ht)

    if bundle.get("reproduction"):
        paragraph("Known-split reproduction of a previously selected fixed configuration. The original held-out split was already known; no new tuning or blinded selection is claimed.")
    heading("Contract diagnostics and interpretation")
    diagnostics = list(data.get("errors", [])) + list(data.get("warnings", [])) + serialization_warnings
    if not diagnostics:
        paragraph("No run-level contract errors. Method-level diagnostics and execution status remain decisive.")
    for message in diagnostics:
        paragraph(str(message))
    resource_text = json.dumps({"supervision_required": data.get("supervision_required"), "resource_validation": data.get("resource_validation"),
                                "resource": data.get("resource"), "execution_runtime": data.get("execution_runtime")}, indent=2, ensure_ascii=False)
    markdown.append("<pre>" + _h(resource_text) + "</pre>\n")
    markup.append("<pre>" + _h(resource_text) + "</pre>")
    paragraph("Precision@k divides by k, including unfilled ranks. Recall/MRR/nDCG are macro averages over answerable queries. Unanswerable results are retrieval false positives, not generated-answer or hallucination measurements; failed requests do not count as successful abstention. Precision oracle ceilings expose sparse labels; they do not alter arithmetic or establish a general precision target. p95 latency uses nearest-rank over all observed queries, including failures.")
    heading("Method results")
    methods = data.get("methods", [])
    headers = ["Method", "Execution", "Valid", "Answerable", "Recall@k", "Precision@k", "Precision ceiling", "MRR@k", "nDCG@k", "p95 ms"]
    rows = []
    for method in methods:
        summary = method.get("summary") or {}
        rows.append([method.get("name"), method.get("status"), method.get("valid"), summary.get("answerable_queries"),
                     summary.get("recall_at_k"), summary.get("precision_at_k"), summary.get("precision_at_k_oracle_ceiling"),
                     summary.get("mrr"), summary.get("ndcg_at_k"), summary.get("latency", {}).get("p95_ms")])
    table(headers, rows)
    for method in methods:
        heading(str(method.get("name", "unknown method")), 3)
        for error in _messages(method.get("errors")) + _messages(method.get("reported_errors")):
            paragraph(str(error))
        summary = method.get("summary") or {}
        measurements = method.get("measurements") if isinstance(method.get("measurements"), dict) else {}
        latency = summary.get("latency") or {}
        table(["Load ms", "Index ms", "Query samples", "Mean ms", "p50 ms", "p95 ms", "Peak process RSS bytes"],
              [[measurements.get("load_ms"), measurements.get("index_ms"), latency.get("count"), latency.get("mean_ms"),
                latency.get("p50_ms"), latency.get("p95_ms"), measurements.get("peak_rss_bytes")]])
        paragraph("Process RSS/resource guards are sampled observations with possible between-sample peaks; missing measurements are not zero usage or proof of the memory cap. Resource failures remain reported errors. These values are not platform-independent performance guarantees.")
        details_text = json.dumps({"model_identity": method.get("identity"), "configuration_digest": method.get("configuration_digest"),
                                   "measurements": measurements, "validation_diagnostics": method.get("diagnostics"),
                                   "retrieval_pool": summary.get("retrieval_pool")}, indent=2, ensure_ascii=False)
        markdown.append("<pre>" + _h(details_text) + "</pre>\n")
        markup.append("<pre>" + _h(details_text) + "</pre>")
        table(["Unanswerable", "Successful abstentions", "False-positive queries", "Returned records", "Unavailable", "Error"],
              [[summary.get("unanswerable_queries"), summary.get("unanswerable_abstained"), summary.get("unanswerable_false_positive_queries"),
                summary.get("unanswerable_returned_records"), summary.get("unavailable_queries"), summary.get("error_queries")]])
        table(["Category", "Answerable", "Recall@k", "Precision@k", "Ceiling", "MRR@k", "nDCG@k"],
              [[category, values.get("answerable_queries"), values.get("recall_at_k"), values.get("precision_at_k"),
                values.get("precision_at_k_oracle_ceiling"), values.get("mrr"), values.get("ndcg_at_k")]
               for category, values in sorted(method.get("categories", {}).items())])
        table(["Query", "Category", "Text", "Rationale", "Status", "Valid", "Pool", "Distractors", "Ranked IDs", "Missing relevant IDs", "Recall@k", "Precision@k", "Ceiling", "MRR@k", "nDCG@k", "Diagnostics"],
              [[row.get("query_id"), row.get("category"), row.get("text"), row.get("rationale"), row.get("status"), row.get("valid"),
                row.get("eligible_record_count"), row.get("eligible_distractor_count"), ", ".join(row.get("ranked_ids", [])), ", ".join(str(value) for value in row.get("missing_relevant_ids", [])), (row.get("metrics") or {}).get("recall_at_k"),
                (row.get("metrics") or {}).get("precision_at_k"), (row.get("metrics") or {}).get("precision_at_k_oracle_ceiling"),
                (row.get("metrics") or {}).get("mrr"), (row.get("metrics") or {}).get("ndcg_at_k"), "; ".join(_messages(row.get("errors")) + _messages(row.get("reported_errors")))]
               for row in method.get("queries", [])])
    heading("Provenance and configuration")
    paragraph("Identities bind the measured fixtures, source files, dependencies, configuration and models. Source changes are permitted in a regression comparison; other compatibility requirements still apply.")
    identity_text = json.dumps({"identity": data.get("identity"), "configuration": data.get("configuration"),
                                "configuration_digest": data.get("configuration_digest")}, indent=2, ensure_ascii=False)
    # HTML-escaped preformatted blocks remain data even if fixtures contain closing tags.
    markdown.append("<pre>" + _h(identity_text) + "</pre>\n")
    markup.append("<pre>" + _h(identity_text) + "</pre>")
    if comparison is not None:
        heading("Regression comparison")
        compare = payload["comparison"]
        paragraph(f"Compatible: {compare.get('compatible')}; quality regressed: {compare.get('regressed')}; source changed: {compare.get('source_changed')}.")
        for reason in compare.get("reasons", []):
            paragraph(str(reason))
        table(["Method", "Compatible", "Comparable", "Regressed", "Reasons", "Regressions", "Metric deltas (after minus before)"],
              [[entry.get("name"), entry.get("compatible"), entry.get("comparable"), entry.get("regressed"),
                "; ".join(entry.get("reasons", [])), "; ".join(entry.get("regressions", [])),
                json.dumps(entry.get("deltas", {}), sort_keys=True)] for entry in compare.get("methods", [])])
    css = "body{font:15px system-ui,sans-serif;line-height:1.5;margin:2rem;max-width:1500px;color:#17202a}table{border-collapse:collapse;display:block;overflow:auto;margin:1rem 0}th,td{border:1px solid #ccd1d1;padding:.4rem;text-align:left;vertical-align:top}th{background:#edf2f7}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f6;padding:1rem}.scope{border-left:4px solid #b9770e;padding:1rem;background:#fef5e7}"
    document = "<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><meta http-equiv=Content-Security-Policy content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\"><title>" + _h(title) + "</title><style>" + css + "</style></head><body>" + "\n".join(markup) + "</body></html>\n"
    paths = {"json": str(output / "report.json"), "markdown": str(output / "report.md"), "html": str(output / "report.html")}
    write_json(paths["json"], payload)
    Path(paths["markdown"]).write_text("\n".join(markdown), encoding="utf-8", newline="\n")
    Path(paths["html"]).write_text(document, encoding="utf-8", newline="\n")
    return paths
