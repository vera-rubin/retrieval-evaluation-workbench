"""Small shared evaluation contracts. Only the lead edits this module."""
from __future__ import annotations

import hashlib
import gzip
import json
import math
import zlib
from pathlib import Path
from typing import Any, Protocol

CORPUS_SCHEMA = "hippo-corpus/v1"
QUERY_SCHEMA = "hippo-queries/v1"
RUN_SCHEMA = "hippo-eval-run/v2"
CONFIG_SCHEMA = "hippo-eval-config/v1"
METRIC_VERSION = "hippo-metrics/v1"
Record = dict[str, Any]
Query = dict[str, Any]


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def body_digest(body: str | None) -> str | None:
    return None if body is None else hashlib.sha256(body.encode("utf-8")).hexdigest()


def load_json(path: str | Path) -> dict:
    def reject_constant(value: str):
        raise ValueError(f"Non-finite JSON constant: {value}")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON number exceeds finite range")
        return number
    path = Path(path)
    max_bytes = 64 * 1024**2
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("JSON input exceeds the 64 MiB workbench bound")
        raw = data.decode("utf-8")
    except (EOFError, zlib.error) as exc:
        raise ValueError("Truncated or malformed compressed JSON") from exc
    return json.loads(raw, parse_constant=reject_constant,
                      object_pairs_hook=unique_object, parse_float=finite_float)


def write_json(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(raw.encode("utf-8"), mtime=0))
    else:
        path.write_text(raw, encoding="utf-8", newline="\n")


def eligible(record: Record, query: Query) -> bool:
    """Synthetic scope/status rules, never authenticated authorization."""
    if record.get("body") is None:
        return False
    rules = query["rules"]
    for plural, singular in (("projects", "project"), ("owners", "owner"),
                             ("tasks", "task"), ("statuses", "status"),
                             ("epistemics", "epistemic"), ("revisions", "revision")):
        permitted = rules[plural]
        if permitted is not None and record.get(singular) not in permitted:
            return False
    if rules["require_evidence"] and not any(
        source.get("availability") == "retained" for source in record["provenance"]
    ):
        return False
    return True


class RetrievalAdapter(Protocol):
    """Evaluate a future implementation by supplying observed search/fetch.

    Engines must return finite scores and unique record IDs. Search receives
    an explicit synthetic eligible-ID set; it is not a runtime capability.
    Build returns measurements, identity supplies actual backend/model pins.
    """
    name: str
    identity: dict

    def build(self, records: list[Record], config: dict) -> dict: ...
    def search(self, query: Query, eligible_ids: set[str], k: int) -> list[dict]: ...
    def fetch(self, record_id: str) -> Record: ...
    def close(self) -> None: ...


DEFAULT_CONFIG = {
    "schema": CONFIG_SCHEMA, "id": "initial-240-rrf60",
    "k": 10, "chunk_tokens": 240, "overlap_tokens": 32,
    "rrf_k": 60, "lexical_weight": 1.0, "semantic_weight": 1.0,
    "seed": 17, "cpu_threads": 2, "max_rss_bytes": 2147483648,
}
