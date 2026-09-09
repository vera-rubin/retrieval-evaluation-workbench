"""Deterministically materialize authored synthetic cases; never read run results."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from hippo_eval.contracts import body_digest, write_json
from hippo_eval.fixtures import validate_fixtures
from cases_development import CASES as DEVELOPMENT
from cases_heldout import CASES as HELDOUT
from cases_development_systems import CASES as DEVELOPMENT_SYSTEMS
from cases_development_operations import CASES as DEVELOPMENT_OPERATIONS
from cases_heldout_systems import CASES as HELDOUT_SYSTEMS
from cases_heldout_operations import CASES as HELDOUT_OPERATIONS

DEVELOPMENT = DEVELOPMENT + DEVELOPMENT_SYSTEMS + DEVELOPMENT_OPERATIONS
HELDOUT = HELDOUT + HELDOUT_SYSTEMS + HELDOUT_OPERATIONS

# Each ordinary query searches a plausible multi-project workspace, not just
# its small authored family. Explicit task/owner/revision cases remain narrow.
WORKSPACES = [
    ("creative-workspace", {"Canvas", "Atlas", "Quill", "Mosaic", "Summit"}),
    ("service-workspace", {"Harbor", "Beacon", "Relay", "Ember", "Fern"}),
    ("operations-workspace", {"Ledger", "Kiln", "Cedar", "Lumen", "Rivet"}),
    ("field-workspace", {"Orchard", "Tide", "Cobalt", "Copper", "Delta"}),
    ("content-workspace", {"Juniper", "Slate", "Opal", "Quartz", "Birch"}),
    ("control-workspace", {"Willow", "Spruce", "Marina", "Kestrel", "Violet"}),
]

AUTHORSHIP = {
    "type": "synthetic-model-assisted",
    "author": "OpenAI Codex",
    "human_validated": False,
    "real_project_data": False,
    "record_epistemics": "Invented story-world statuses, not real verification claims.",
    "label_basis": "Authored from explicit record text and declared scope rules before retrieval output.",
    "split_policy": "Distinct authored family/story sets allocated before tuning; no family crosses splits.",
    "blinding_limit": "The fixture author can see both splits. Family separation is not an independently curated blind benchmark.",
    "coverage_limit": "Synthetic English technical stories; not representative production evidence or authenticated authorization.",
    "relevance_convention": "3: direct answer or independently requested component; 2: explicit partial answer or corroboration; 1: useful illustration/context; absent: nonrelevant or ineligible. Labels include explicit corroboration but remain fallible synthetic judgments.",
    "workspace_pool_policy": "Ordinary queries allow five related projects and their authors, with tasks unrestricted. Explicit scope/history questions may have small eligible sets; report them separately.",
    "levels": "1: synthetic episode/fact; 2: private preference or synthesis; 3: verified story-world shared decision owned by Hive. These labels do not execute actual storage or promotion.",
    "provenance_representation": "Source IDs and availability are symbolic story-world provenance, not real retained source files or human verification. No external source content is asserted.",
}


def materialize():
    records, queries = [], []
    for split, cases in (("development", DEVELOPMENT), ("heldout", HELDOUT)):
        for case in cases:
            family = case["family"]
            workspace_name, workspace_projects = next((name, projects) for name, projects in WORKSPACES if case["project"] in projects)
            workspace_owners = sorted({member["owner"] for member in cases if member["project"] in workspace_projects} | {"Hive"})
            record_ids = {item["key"]: f"r-{family}-{item['key']}" for item in case["records"]}
            for item in case["records"]:
                provenance = item.get("provenance", "retained")
                if isinstance(provenance, str):
                    provenance = [{"source_id": f"synthetic-source-{family}-{item['key']}",
                                   "revision": item["revision"], "availability": provenance}]
                record = {name: item[name] for name in ("title", "body", "kind", "status", "epistemic", "revision")}
                record.update(id=record_ids[item["key"]], family=family,
                              project=item.get("project", case["project"]),
                              owner=item.get("owner", case["owner"]),
                              task=item.get("task", case["task"]), level=item.get("level", 1),
                              body_sha256=body_digest(item["body"]), provenance=provenance,
                              supersedes=[record_ids[key] for key in item.get("supersedes", [])])
                records.append(record)
            for item in case["queries"]:
                rules = dict(projects=sorted(workspace_projects), owners=workspace_owners, tasks=None,
                             statuses=["current"], epistemics=["supported", "verified"],
                             revisions=None, require_evidence=True)
                rules.update(item["rules"])
                relevance = {record_ids[key]: grade for key, grade in item["relevance"].items()}
                queries.append(dict(id=f"q-{family}-{item['key']}", split=split, family=family,
                                    category=item["category"], text=item["text"], relevance=relevance,
                                    rationale=item["rationale"] + f" Applicability: {workspace_name}; explicit query rules control project, owner, task, status, epistemic state, revision, and evidence eligibility.",
                                    answerable=bool(relevance), rules=rules))
    return (dict(schema="hippo-corpus/v1", version="synthetic-workspace-stories-v2-public1", authorship=AUTHORSHIP, records=records),
            dict(schema="hippo-queries/v1", version="synthetic-workspace-stories-v2-public1", authorship=AUTHORSHIP, queries=queries))


if __name__ == "__main__":
    corpus, queries = materialize()
    audit = validate_fixtures(corpus, queries)
    if not audit["valid"]:
        raise SystemExit(json.dumps(audit, indent=2))
    write_json(ROOT / "fixtures" / "corpus.json", corpus)
    write_json(ROOT / "fixtures" / "queries.json", queries)
    write_json(ROOT / "fixtures" / "audit.json", audit)
    display = dict(audit, summary=dict(audit["summary"]))
    display["summary"]["eligible_pools"] = {key: value for key, value in audit["summary"]["eligible_pools"].items() if key != "per_query"}
    print(json.dumps(display, indent=2))
