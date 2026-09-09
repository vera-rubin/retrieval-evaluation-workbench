"""Disposable synthetic retrieval adapters; no authenticated authority or broker.

Only title/body enter retrieval. Callers supply synthetic eligible IDs; canonical
fetch returns an independent copy of the complete original record. Model loading
is local-only and pinned; missing artifacts are errors rather than mock scores.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys
import time
from typing import Any

from .contracts import digest

MODEL_SPECS = {
    "bge": {
        "model_id": "BAAI/bge-small-en-v1.5",
        "revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a",
        "pooling": "cls", "max_sequence_tokens": 512,
        "query_prefix": "Represent this sentence for searching relevant passages: ",
    },
    "minilm": {
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "pooling": "attention_mask_mean", "max_sequence_tokens": 256,
        "query_prefix": "",
    },
}


class RetrievalUnavailable(RuntimeError):
    pass


class RetrievalMissing(RetrievalUnavailable):
    """Required local runtime or artifacts are absent; no inference was attempted."""


class RetrievalInputError(ValueError):
    pass


def _sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024**2), b""):
            result.update(block)
    return result.hexdigest()


def _rss_bytes() -> int:
    """Current owned-process RSS, with no inspection of other processes."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        info = Counters()
        info.cb = ctypes.sizeof(info)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        api = ctypes.WinDLL("psapi", use_last_error=True)
        api.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        if not api.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(info), info.cb):
            raise OSError(ctypes.get_last_error(), "Cannot measure own process RSS")
        return int(info.WorkingSetSize)
    try:
        import resource
        scale = 1 if sys.platform == "darwin" else 1024
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * scale)
    except ImportError as exc:
        raise RetrievalUnavailable("RSS measurement unavailable on this platform") from exc


def _validated_config(config: dict) -> dict:
    result = dict(config)
    for key, default in (("chunk_tokens", 240), ("overlap_tokens", 32),
                         ("rrf_k", 60), ("cpu_threads", 2),
                         ("max_rss_bytes", 2 * 1024**3), ("seed", 17)):
        result.setdefault(key, default)
    for key, default in (("lexical_weight", 1.0), ("semantic_weight", 1.0)):
        result.setdefault(key, default)
        if not isinstance(result[key], (int, float)) or not math.isfinite(result[key]) or result[key] <= 0:
            raise RetrievalInputError(f"Invalid {key}")
    if not 1 <= result["cpu_threads"] <= 2:
        raise RetrievalInputError("CPU thread budget must be one or two")
    if not 0 < result["max_rss_bytes"] <= 2 * 1024**3:
        raise RetrievalInputError("RSS limit must be positive and at most 2 GiB")
    if result["rrf_k"] <= 0:
        raise RetrievalInputError("RRF constant must be positive")
    if not 4 <= result["chunk_tokens"] <= 512:
        raise RetrievalInputError("Invalid chunk token budget")
    if not 0 <= result["overlap_tokens"] < result["chunk_tokens"] - 2:
        raise RetrievalInputError("Overlap must be smaller than passage token capacity")
    return result


def _safe_fts_query(text: str) -> str | None:
    """Bounded literal Unicode terms joined with OR; never execute user syntax."""
    if not isinstance(text, str):
        raise RetrievalInputError("Query text must be a string")
    terms = list(dict.fromkeys(re.findall(r"[^\W_]+(?:_[^\W_]+)*", text, re.UNICODE)))
    if len(terms) > 256:
        raise RetrievalInputError("LEXICAL_QUERY_TOO_LONG: more than 256 terms")
    return " OR ".join('"' + term.replace('"', '""') + '"' for term in terms) or None


def _check_records(records: list[dict]) -> dict[str, dict]:
    originals: dict[str, dict] = {}
    for record in records:
        rid = record.get("id")
        if not isinstance(rid, str) or not rid or rid in originals:
            raise RetrievalInputError("Missing or duplicate canonical record ID")
        if not isinstance(record.get("title"), str):
            raise RetrievalInputError(f"Invalid title: {rid}")
        body = record.get("body")
        if body is not None and not isinstance(body, str):
            raise RetrievalInputError(f"Invalid body: {rid}")
        actual = None if body is None else hashlib.sha256(body.encode("utf-8")).hexdigest()
        if record.get("body_sha256") != actual:
            raise RetrievalInputError(f"Canonical body digest mismatch: {rid}")
        originals[rid] = copy.deepcopy(record)
    return originals


class LexicalEngine:
    def __init__(self):
        self.name = "lexical"
        self.identity = {"method": "lexical", "backend": "apsw_fts5_bm25",
                         "query_terms": "literal_unicode_or/v1",
                         "corpus_statistics": "whole_synthetic_build",
                         "eligibility": "bound_rowids_before_order_and_limit",
                         "indexed_fields": ["title", "body"],
                         "synthetic_eligibility_is_authority": False}
        self._records: dict[str, dict] = {}
        self._db = None
        self._active_ids: tuple[str, ...] | None = None

    def _install_scope(self, ids: tuple[str, ...]) -> None:
        if ids == self._active_ids:
            return
        self._db.execute("BEGIN")
        try:
            self._db.execute("DELETE FROM eligible_fts")
            for rowid, rid in enumerate(ids, 1):
                record = self._records[rid]
                self._db.execute("INSERT INTO eligible_fts(rowid,title,body) VALUES(?,?,?)",
                                 (rowid, record["title"], record["body"]))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        self._active_ids = ids

    def build(self, records: list[dict], config: dict) -> dict:
        self.close()
        started = time.perf_counter()
        try:
            import apsw
        except ImportError as exc:
            raise RetrievalMissing("APSW_NOT_STAGED") from exc
        self.config = _validated_config(config)
        self._records = _check_records(records)
        self._db = apsw.Connection(":memory:")
        self._db.execute("CREATE VIRTUAL TABLE eligible_fts USING fts5(title,body,tokenize='unicode61')")
        self.identity.update(apsw=apsw.apswversion(), sqlite=apsw.sqlitelibversion())
        loaded = time.perf_counter()
        ids = tuple(sorted(rid for rid, record in self._records.items() if record["body"] is not None))
        self._install_scope(ids)
        return {"load_ms": (loaded - started) * 1000,
                "index_ms": (time.perf_counter() - loaded) * 1000,
                "indexed_records": len(ids), "indexed_chunks": len(ids),
                "peak_rss_bytes": _rss_bytes(),
                "scope_index_rebuild_in_query_latency": False}

    def search(self, query: dict, eligible_ids: set[str], k: int) -> list[dict]:
        if self._db is None:
            raise RetrievalUnavailable("Engine is not built")
        if k < 0:
            raise RetrievalInputError("k must be non-negative")
        if not eligible_ids.issubset(self._records):
            raise RetrievalInputError("Eligible set contains unknown record IDs")
        if k == 0:
            return []
        ids = tuple(sorted(rid for rid in eligible_ids if self._records[rid]["body"] is not None))
        expression = _safe_fts_query(query["text"])
        if not ids or expression is None:
            return []
        rowids = {rid: index for index, rid in enumerate(self._active_ids, 1)}
        eligible_rowids = [rowids[rid] for rid in ids]
        if len(eligible_rowids) > 10000:
            raise RetrievalInputError("Eligible fixture set exceeds bounded SQL parameter budget")
        placeholders = ",".join("?" for _ in eligible_rowids)
        found = list(self._db.execute(
            "SELECT rowid,bm25(eligible_fts) FROM eligible_fts WHERE eligible_fts MATCH ? AND rowid IN (" + placeholders + ") ORDER BY bm25(eligible_fts),rowid LIMIT ?",
            (expression, *eligible_rowids, k)))
        return [{"record_id": self._active_ids[rowid - 1], "score": -float(score)} for rowid, score in found]

    def fetch(self, record_id: str) -> dict:
        if record_id not in self._records:
            raise KeyError(record_id)
        return copy.deepcopy(self._records[record_id])

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
        self._db = None
        self._active_ids = None


def tokenizer_chunks(text: str, tokenizer: Any, token_budget: int, overlap: int,
                     record_id: str, field: str) -> list[dict]:
    """Exact source substrings, preserving whitespace and UTF-8 offset provenance.

    The budget includes special tokens. Retokenize every substring to catch
    WordPiece boundary changes; never rely on tokenizer truncation.
    """
    if not text or not text.strip():
        return []
    special = tokenizer.num_special_tokens_to_add(pair=False)
    capacity = token_budget - special
    if capacity <= overlap or overlap < 0:
        raise RetrievalInputError("Impossible tokenizer/chunk budget")
    encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True,
                        truncation=False, verbose=False)
    offsets = encoded["offset_mapping"]
    if not offsets:
        return []
    byte_offsets = [0]
    for character in text:
        byte_offsets.append(byte_offsets[-1] + len(character.encode("utf-8")))
    chunks = []
    start = 0
    while start < len(offsets):
        end = min(start + capacity, len(offsets))
        char_start = 0 if start == 0 else offsets[start][0]
        while end > start:
            char_end = len(text) if end == len(offsets) else offsets[end][0]
            fragment = text[char_start:char_end]
            count = len(tokenizer(fragment, add_special_tokens=True, truncation=False,
                                  verbose=False)["input_ids"])
            if count <= token_budget:
                break
            end -= 1
        if end <= start or char_end <= char_start:
            raise RetrievalInputError("Cannot make progress without truncating a source token")
        index = len(chunks)
        chunks.append({"chunk_id": f"{record_id}:{field}:{index}", "record_id": record_id,
                       "field": field, "char_start": char_start, "char_end": char_end,
                       "byte_start": byte_offsets[char_start], "byte_end": byte_offsets[char_end],
                       "token_count": count, "text": fragment,
                       "text_sha256": hashlib.sha256(fragment.encode("utf-8")).hexdigest(),
                       "source_field_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()})
        if end == len(offsets):
            break
        start = max(start + 1, end - overlap)
    return chunks


class SemanticEngine:
    def __init__(self, model_key: str, artifact_root: str | Path | None = None):
        self.name = model_key
        self.spec = dict(MODEL_SPECS[model_key])
        self.artifact_root = Path(artifact_root) if artifact_root else Path(__file__).resolve().parents[1] / ".artifacts"
        self.identity = {"method": model_key, "backend": "pytorch_cpu_fp32_exact_cosine",
                         **self.spec, "dimensions": 384, "normalization": "l2",
                         "indexed_fields": ["title", "body"],
                         "chunking": "fast_tokenizer_exact_field_offsets/v1",
                         "synthetic_eligibility_is_authority": False}
        self._records = {}
        self._chunks = []
        self._vectors = None
        self._model = None
        self._tokenizer = None
        self._peak_rss = 0

    def _check_memory(self):
        current = _rss_bytes()
        self._peak_rss = max(self._peak_rss, current)
        if current > self.config["max_rss_bytes"]:
            raise RetrievalUnavailable(f"RSS_LIMIT_EXCEEDED: {current}")

    def _load(self):
        model_dir = self.artifact_root / "models" / self.name
        manifest_path = model_dir / "manifest.json"
        if not manifest_path.is_file():
            raise RetrievalMissing(f"MODEL_NOT_STAGED: {self.spec['model_id']}@{self.spec['revision']}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("model_id") != self.spec["model_id"] or manifest.get("revision") != self.spec["revision"]:
            raise RetrievalUnavailable("MODEL_IDENTITY_MISMATCH")
        for file in manifest["files"]:
            path = model_dir / file["path"]
            if not path.resolve().is_relative_to(model_dir.resolve()) or _sha(path) != file["sha256"]:
                raise RetrievalUnavailable("MODEL_ARTIFACT_HASH_MISMATCH")
        try:
            import torch
            import transformers
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RetrievalMissing(f"CPU_RUNTIME_NOT_STAGED: {exc}") from exc
        torch.set_num_threads(self.config["cpu_threads"])
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            if torch.get_num_interop_threads() != 1:
                raise RetrievalUnavailable("Existing interop thread count violates process budget")
        torch.manual_seed(self.config["seed"])
        self._tokenizer = AutoTokenizer.from_pretrained(str(model_dir), use_fast=True,
                                                        trust_remote_code=False, local_files_only=True)
        if not self._tokenizer.is_fast:
            raise RetrievalUnavailable("Fast tokenizer offsets are required")
        self._model = AutoModel.from_pretrained(str(model_dir), use_safetensors=True,
                                               trust_remote_code=False, local_files_only=True,
                                               dtype=torch.float32).to("cpu").eval()
        self.identity.update(torch=torch.__version__, transformers=transformers.__version__,
                             tokenizer=importlib.metadata.version("tokenizers"),
                             tokenizer_class=type(self._tokenizer).__name__,
                             model_class=type(self._model).__name__,
                             attention_implementation=self._model.config._attn_implementation,
                             model_manifest_sha256=_sha(manifest_path),
                             artifact_hashes={item["path"]: item["sha256"] for item in manifest["files"]})
        self._check_memory()

    def _encode(self, texts: list[str]):
        import numpy as np
        import torch
        output = []
        for start in range(0, len(texts), 8):
            batch = texts[start:start + 8]
            inputs = self._tokenizer(batch, padding=True, truncation=False, return_tensors="pt",
                                     verbose=False)
            if inputs["input_ids"].shape[1] > self.spec["max_sequence_tokens"]:
                raise RetrievalInputError("MODEL_INPUT_TOO_LONG: no truncation performed")
            with torch.inference_mode():
                hidden = self._model(**inputs).last_hidden_state
                if self.spec["pooling"] == "cls":
                    pooled = hidden[:, 0]
                else:
                    mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
                    pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
                if not torch.isfinite(pooled).all() or (pooled.norm(dim=1) == 0).any():
                    raise RetrievalUnavailable("Invalid model vector")
                normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
                output.append(normalized.cpu().numpy().copy())
            self._check_memory()
        return np.concatenate(output, axis=0) if output else np.empty((0, 384), dtype=np.float32)

    def build(self, records: list[dict], config: dict) -> dict:
        self.close()
        self._peak_rss = 0
        started = time.perf_counter()
        self.config = _validated_config(config)
        if self.config["chunk_tokens"] > self.spec["max_sequence_tokens"]:
            raise RetrievalInputError("Chunk budget exceeds model input limit")
        self._records = _check_records(records)
        self._load()
        loaded = time.perf_counter()
        self._chunks = []
        for rid in sorted(self._records):
            record = self._records[rid]
            if record["body"] is None:
                continue
            for field in ("title", "body"):
                self._chunks.extend(tokenizer_chunks(record[field], self._tokenizer,
                                                     self.config["chunk_tokens"], self.config["overlap_tokens"], rid, field))
        self._vectors = self._encode([chunk["text"] for chunk in self._chunks])
        if self._vectors.shape != (len(self._chunks), 384):
            raise RetrievalUnavailable("Unexpected embedding shape")
        return {"load_ms": (loaded - started) * 1000,
                "index_ms": (time.perf_counter() - loaded) * 1000,
                "indexed_records": len({item["record_id"] for item in self._chunks}),
                "indexed_chunks": len(self._chunks), "peak_rss_bytes": self._peak_rss,
                "resource_details": {"cpu_threads": self.config["cpu_threads"], "interop_threads": 1,
                                     "batch_size": 8, "device": "cpu", "dtype": "float32",
                                     "engine_rss_measurement": "own_process_samples_after_load_and_each_batch"}}

    def search(self, query: dict, eligible_ids: set[str], k: int) -> list[dict]:
        if self._vectors is None:
            raise RetrievalUnavailable("Engine is not built")
        if not eligible_ids.issubset(self._records):
            raise RetrievalInputError("Eligible set contains unknown record IDs")
        if k < 0:
            raise RetrievalInputError("k must be non-negative")
        if not eligible_ids or k == 0:
            return []
        text = self.spec["query_prefix"] + query["text"]
        vector = self._encode([text])[0]
        indices = [i for i, chunk in enumerate(self._chunks) if chunk["record_id"] in eligible_ids]
        if not indices:
            return []
        similarities = self._vectors[indices] @ vector
        best = {}
        for index, similarity in zip(indices, similarities):
            chunk = self._chunks[index]
            score = float(similarity)
            rid = chunk["record_id"]
            prior = best.get(rid)
            if prior is None or score > prior["score"] or (score == prior["score"] and chunk["chunk_id"] < prior["chunk_ids"][0]):
                best[rid] = {"record_id": rid, "score": score, "chunk_ids": [chunk["chunk_id"]],
                             "chunks": [copy.deepcopy(chunk)]}
        return sorted(best.values(), key=lambda item: (-item["score"], item["record_id"]))[:k]

    def fetch(self, record_id: str) -> dict:
        if record_id not in self._records:
            raise KeyError(record_id)
        return copy.deepcopy(self._records[record_id])

    def close(self) -> None:
        self._model = None
        self._tokenizer = None
        self._vectors = None
        self._chunks = []
        import gc
        gc.collect()


class HybridEngine:
    def __init__(self, model_key: str, artifact_root: str | Path | None):
        self.name = "hybrid_" + model_key
        self.lexical = LexicalEngine()
        self.semantic = SemanticEngine(model_key, artifact_root)
        self.identity = {"method": self.name, "fusion": "record_level_weighted_rrf/v1"}

    def build(self, records: list[dict], config: dict) -> dict:
        self.config = _validated_config(config)
        try:
            lex = self.lexical.build(records, config)
            sem = self.semantic.build(records, config)
        except Exception:
            self.close()
            raise
        self.identity.update(lexical=self.lexical.identity, semantic=self.semantic.identity)
        return {"load_ms": lex["load_ms"] + sem["load_ms"],
                "index_ms": lex["index_ms"] + sem["index_ms"],
                "indexed_chunks": sem["indexed_chunks"],
                "indexed_records": sem["indexed_records"],
                "peak_rss_bytes": max(lex["peak_rss_bytes"], sem["peak_rss_bytes"]),
                "scope_index_rebuild_in_query_latency": False}

    def search(self, query: dict, eligible_ids: set[str], k: int) -> list[dict]:
        if k < 0:
            raise RetrievalInputError("k must be non-negative")
        if k == 0:
            return []
        fused = {}
        for engine, weight in ((self.lexical, self.config["lexical_weight"]),
                               (self.semantic, self.config["semantic_weight"])):
            for rank, item in enumerate(engine.search(query, eligible_ids, len(eligible_ids)), 1):
                rid = item["record_id"]
                entry = fused.setdefault(rid, {"record_id": rid, "score": 0.0})
                entry["score"] += weight / (self.config["rrf_k"] + rank)
                if "chunks" in item:
                    entry["chunks"] = item["chunks"]
                    entry["chunk_ids"] = item["chunk_ids"]
        return sorted(fused.values(), key=lambda item: (-item["score"], item["record_id"]))[:k]

    def fetch(self, record_id: str) -> dict:
        return self.semantic.fetch(record_id)

    def close(self) -> None:
        self.lexical.close()
        self.semantic.close()


def create_engine(name: str, artifact_root: str | Path | None = None):
    if name == "lexical":
        return LexicalEngine()
    if name in MODEL_SPECS:
        return SemanticEngine(name, artifact_root)
    if name in ("hybrid_bge", "hybrid_minilm"):
        return HybridEngine(name.removeprefix("hybrid_"), artifact_root)
    raise RetrievalInputError(f"Unknown retrieval engine: {name}")
