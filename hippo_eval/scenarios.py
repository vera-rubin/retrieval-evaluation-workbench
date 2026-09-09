"""Check literal observable traces against separate synthetic oracles.

This executes a trace checker, not a memory broker. It cannot establish that
authentication, persistence, process fencing or recovery work.
"""
from __future__ import annotations

import math
from typing import Any

SCENARIO_SCHEMA = "hippo-memory-scenarios/v1"
TRACE_SCHEMA = "hippo-memory-traces/v1"
CHECK_SCHEMA = "hippo-memory-trace-check/v1"


def _valid_json(value: Any) -> bool:
    if value is None or type(value) in (str, int, bool):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_valid_json(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _valid_json(item) for key, item in value.items())
    return False


def _differences(expected: Any, observed: Any, path: str) -> list[str]:
    """Exact keys/types matter: true is not 1; extra metadata can be a leak."""
    if type(expected) is not type(observed):
        return [f"{path}: expected type {type(expected).__name__}, observed {type(observed).__name__}"]
    if isinstance(expected, dict):
        errors = []
        for key in sorted(set(expected) - set(observed)):
            errors.append(f"{path}.{key}: missing observable")
        for key in sorted(set(observed) - set(expected)):
            errors.append(f"{path}.{key}: unexpected observable/possible disclosure")
        for key in sorted(set(expected) & set(observed)):
            errors.extend(_differences(expected[key], observed[key], f"{path}.{key}"))
        return errors
    if isinstance(expected, list):
        errors = []
        if len(expected) != len(observed):
            errors.append(f"{path}: expected {len(expected)} items, observed {len(observed)}")
        for index, (left, right) in enumerate(zip(expected, observed)):
            errors.extend(_differences(left, right, f"{path}[{index}]"))
        return errors
    return [] if expected == observed else [f"{path}: expected {expected!r}, observed {observed!r}"]


def _cases(value: Any, schema: str, label: str, errors: list[str]) -> dict:
    if not isinstance(value, dict) or value.get("schema") != schema:
        errors.append(f"{label}: unsupported/missing schema")
        return {}
    if value.get("synthetic") is not True:
        errors.append(f"{label}.synthetic: must explicitly be true")
    authorship = value.get("authorship")
    if not isinstance(authorship, dict) or authorship.get("method") not in ("hand_authored", "model_authored_literal_examples") or not isinstance(authorship.get("review"), str) or not authorship["review"].strip():
        errors.append(f"{label}.authorship: recognized authorship method and review note required")
    if not isinstance(value.get("version"), str) or not value["version"].strip():
        errors.append(f"{label}.version: required")
    if not isinstance(value.get("cases"), list) or not value["cases"]:
        errors.append(f"{label}.cases: nonempty array required")
        return {}
    output = {}
    for index, case in enumerate(value["cases"]):
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"].strip():
            errors.append(f"{label}.cases[{index}]: malformed case ID")
            continue
        if case["id"] in output:
            errors.append(f"{label}.cases: duplicate case ID {case['id']}")
        output[case["id"]] = case
        steps = case.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{label}.{case['id']}.steps: nonempty array required")
            continue
        ids = set()
        field = "expect" if schema == SCENARIO_SCHEMA else "observed"
        for step_index, step in enumerate(steps):
            if not isinstance(step, dict) or not isinstance(step.get("id"), str) or not step["id"].strip():
                errors.append(f"{label}.{case['id']}.steps[{step_index}]: malformed step ID")
                continue
            if step["id"] in ids:
                errors.append(f"{label}.{case['id']}: duplicate step ID {step['id']}")
            ids.add(step["id"])
            if not isinstance(step.get(field), dict) or not _valid_json(step[field]):
                errors.append(f"{label}.{case['id']}.{step['id']}.{field}: expected finite JSON object")
    return output


def check_traces(scenarios: Any, traces: Any) -> dict:
    """Strictly check complete traces; supplied 'correct' labels never force a pass."""
    errors: list[str] = []
    result = {"schema": CHECK_SCHEMA, "valid": False, "errors": errors, "cases": [],
              "execution": "executed_checker_on_literal_synthetic_observations",
              "product_execution": {"authenticated identity and security": "NOT RUN", "canonical transactions and persistence": "NOT RUN",
                                    "process replacement and fencing": "NOT RUN", "live recovery and backups": "NOT RUN"}}
    expected = _cases(scenarios, SCENARIO_SCHEMA, "scenarios", errors)
    observed = _cases(traces, TRACE_SCHEMA, "traces", errors)
    if set(expected) != set(observed):
        errors.append(f"case coverage: missing={sorted(set(expected) - set(observed))}, unknown={sorted(set(observed) - set(expected))}")
    if errors:
        result["summary"] = {"expected_cases": len(expected), "observed_cases": len(observed), "passed": 0, "failed": 0, "schema_valid": False}
        return result
    for case_id, case in expected.items():
        actual = observed[case_id]
        findings = []
        expected_steps = [step["id"] for step in case["steps"]]
        actual_steps = [step["id"] for step in actual["steps"]]
        if expected_steps != actual_steps:
            findings.append(f"{case_id}.steps: missing, extra, or reordered observations; expected={expected_steps}, observed={actual_steps}")
        actual_by_id = {step["id"]: step for step in actual["steps"]}
        step_results = []
        for step in case["steps"]:
            step_id = step["id"]
            if step_id not in actual_by_id:
                step_errors = [f"{case_id}.{step_id}: missing observation"]
            else:
                step_errors = _differences(step["expect"], actual_by_id[step_id]["observed"], f"{case_id}.{step_id}")
            findings.extend(step_errors)
            step_results.append({"id": step_id, "passed": not step_errors, "errors": step_errors})
        result["cases"].append({"id": case_id, "title": case.get("title"), "source_scenarios": case.get("source_scenarios", []),
                                "passed": not findings, "errors": findings, "steps": step_results})
        errors.extend(findings)
    result["valid"] = not errors
    result["summary"] = {"expected_cases": len(expected), "observed_cases": len(observed),
                          "passed": sum(case["passed"] for case in result["cases"]),
                          "failed": sum(not case["passed"] for case in result["cases"]), "schema_valid": True}
    return result
