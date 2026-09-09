"""Command integration for the standalone retrieval evaluation workbench."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fnmatch
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest
import uuid

from .contracts import (DEFAULT_CONFIG, METRIC_VERSION, RUN_SCHEMA,
                        body_digest, digest, eligible, load_json, write_json)
from .bootstrap import (artifact_root as _artifact_root,
                        artifact_site as _artifact_site,
                        bootstrap_artifact_site as _bootstrap_artifact_site)

ROOT = Path(__file__).resolve().parents[1]
METHODS = ["lexical", "bge", "minilm", "hybrid_bge", "hybrid_minilm"]
LOCK_SCHEMA = "hippo-eval-inference-lock/v2"
LOCK_GATE_ATTEMPTS = 20


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifact_root(value=None) -> Path:
    return _artifact_root(value, ROOT / ".artifacts")


def artifact_site(value=None) -> Path:
    return _artifact_site(value, ROOT / ".artifacts")


def bootstrap_artifact_site(value=None) -> Path:
    return _bootstrap_artifact_site(value, ROOT / ".artifacts")


def _distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def source_identity(selected_artifacts=None) -> dict:
    files = sorted((ROOT / "hippo_eval").glob("*.py")) + [ROOT / "workbench.py"]
    mapping = {str(p.relative_to(ROOT)).replace("\\", "/"):
               hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    try:
        git_root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
                                           text=True, timeout=5, stderr=subprocess.DEVNULL).strip()
        if Path(git_root).resolve() != ROOT.resolve():
            raise ValueError("No standalone Git root")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True, timeout=5, stderr=subprocess.DEVNULL).strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        head = None
    import importlib.metadata
    tracked = ("apsw", "sqlite-vec", "torch", "transformers", "tokenizers",
               "numpy", "safetensors", "huggingface-hub", "sentence-transformers", "psutil")
    dependencies = {name: None for name in tracked}
    staged_site = artifact_site(selected_artifacts)
    if staged_site.is_dir():
        # Inspect only the explicitly staged local dependency closure.
        for distribution in importlib.metadata.distributions(path=[str(staged_site)]):
            name = distribution.metadata.get("Name")
            if name:
                dependencies[_distribution_name(name)] = distribution.version
    dependencies["python"] = sys.version
    base_executable = Path(getattr(sys, "_base_executable", sys.executable))
    dependencies["python_executable_sha256"] = hashlib.sha256(base_executable.read_bytes()).hexdigest()
    return {"source_digest": digest(mapping), "source_files": mapping,
            "git_head": head, "source_origin": "git_checkout" if head else "source_archive",
            "dependencies": dependencies,
            "dependency_digest": digest(dependencies), "metric_version": METRIC_VERSION}


def _workspace_id() -> str:
    canonical = os.path.normcase(str(ROOT.resolve())).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@contextmanager
def _inference_gate(path: Path):
    """Serialize claim transitions; the OS releases this short lock on exit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    locked = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
            os.fsync(fd)
        for attempt in range(LOCK_GATE_ATTEMPTS):
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if attempt + 1 == LOCK_GATE_ATTEMPTS:
                    raise ValueError("Inference lock ownership is being updated; retry later")
                time.sleep(0.025)
        yield
    finally:
        if locked:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _process_reference(psutil_module, pid: int) -> dict:
    process = psutil_module.Process(pid)
    created = float(process.create_time())
    if not math.isfinite(created) or created <= 0:
        raise ValueError("Process creation identity is unavailable")
    return {"pid": pid, "create_time": created}


def _valid_process_reference(value) -> bool:
    return (isinstance(value, dict)
            and isinstance(value.get("pid"), int) and not isinstance(value["pid"], bool)
            and value["pid"] > 0
            and isinstance(value.get("create_time"), (int, float))
            and not isinstance(value["create_time"], bool)
            and math.isfinite(value["create_time"]) and value["create_time"] > 0)


def _process_reference_state(reference: dict, psutil_module) -> str:
    try:
        process = psutil_module.Process(reference["pid"])
        created = float(process.create_time())
        running = process.is_running()
    except psutil_module.NoSuchProcess:
        return "STALE"
    except (psutil_module.AccessDenied, OSError, ValueError):
        return "AMBIGUOUS"
    if not running or created != float(reference["create_time"]):
        return "STALE"
    try:
        status = process.status()
    except psutil_module.NoSuchProcess:
        return "STALE"
    except (psutil_module.AccessDenied, OSError, ValueError):
        return "AMBIGUOUS"
    zombie_status = getattr(psutil_module, "STATUS_ZOMBIE", "zombie")
    if status == zombie_status:
        return "STALE"
    return "LIVE"


def _read_lock_record(lock: Path):
    if lock.is_symlink() or not lock.is_file():
        raise ValueError("Inference lock has an unsafe filesystem type")
    if lock.stat().st_size > 16 * 1024:
        raise ValueError("Inference lock record exceeds its size bound")
    raw = lock.read_text(encoding="utf-8").strip()
    if raw.isdecimal():
        pid = int(raw)
        if pid <= 0:
            raise ValueError("Legacy inference lock PID is invalid")
        return {"legacy_pid": pid}
    try:
        record = json.loads(raw, object_pairs_hook=lambda pairs: (
            (_ for _ in ()).throw(ValueError("Duplicate inference lock field"))
            if len({key for key, _ in pairs}) != len(pairs) else dict(pairs)))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("Inference lock ownership is malformed or ambiguous") from exc
    if not isinstance(record, dict) or record.get("schema") != LOCK_SCHEMA:
        raise ValueError("Inference lock ownership is malformed or ambiguous")
    try:
        token = record["claim_id"]
        parsed_token = uuid.UUID(hex=token)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Inference lock claim identity is malformed") from exc
    if not isinstance(token, str) or parsed_token.hex != token:
        raise ValueError("Inference lock claim identity is malformed")
    boot_time = record.get("boot_time")
    if (not isinstance(boot_time, (int, float)) or isinstance(boot_time, bool)
            or not math.isfinite(boot_time) or boot_time <= 0):
        raise ValueError("Inference lock boot identity is malformed")
    if record.get("workspace_id") != _workspace_id():
        raise ValueError("Inference lock belongs to an ambiguous workspace")
    phase, supervisor, worker = record.get("phase"), record.get("supervisor"), record.get("worker")
    if not _valid_process_reference(supervisor):
        raise ValueError("Inference lock supervisor identity is malformed")
    if phase == "STARTING" and worker is not None:
        raise ValueError("Inference lock starting state is inconsistent")
    if phase == "RUNNING" and not _valid_process_reference(worker):
        raise ValueError("Inference lock worker identity is malformed")
    if phase not in ("STARTING", "RUNNING"):
        raise ValueError("Inference lock phase is malformed")
    return record


def _atomic_write_lock(lock: Path, record: dict) -> None:
    temporary = lock.with_name(f".{lock.name}.{record['claim_id']}.tmp")
    raw = json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.close(fd)
        fd = -1
        os.replace(temporary, lock)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def _lock_owner_state(record, psutil_module) -> tuple[str, str]:
    if "legacy_pid" in record:
        # A v1 PID-only record cannot prove that an orphaned worker has ended,
        # even when its former supervisor PID is now absent.
        return "AMBIGUOUS", "legacy PID-only ownership cannot identify an orphan worker"
    try:
        current_boot = float(psutil_module.boot_time())
    except (OSError, ValueError):
        return "AMBIGUOUS", "host boot identity cannot be read"
    prior_boot = abs(current_boot - float(record["boot_time"])) > 1.0
    states = [_process_reference_state(record["supervisor"], psutil_module)]
    if record["worker"] is not None:
        states.append(_process_reference_state(record["worker"], psutil_module))
    if "LIVE" in states:
        if prior_boot:
            return "AMBIGUOUS", "boot and live process identities are inconsistent"
        return "LIVE", "recorded evaluation process is still active"
    if "AMBIGUOUS" in states:
        return "AMBIGUOUS", "recorded process ownership cannot be proved"
    reason = "lock belongs to a prior host boot" if prior_boot else "all recorded evaluation processes have ended"
    return "STALE", reason


def acquire_inference_lock(lock: Path, psutil_module, plan_digest: str) -> str:
    """Claim the one-inference slot, reclaiming only conclusively stale state."""
    lock = Path(lock)
    gate = lock.with_name("inference.gate")
    with _inference_gate(gate):
        if lock.exists() or lock.is_symlink():
            try:
                existing = _read_lock_record(lock)
                state, reason = _lock_owner_state(existing, psutil_module)
            except ValueError as exc:
                raise ValueError(f"Inference lock is unsafe to reclaim: {exc}") from exc
            if state != "STALE":
                raise ValueError(f"Inference lock remains protected ({state}): {reason}")
            quarantine = lock.with_name(f".{lock.name}.stale.{uuid.uuid4().hex}")
            os.replace(lock, quarantine)
            quarantine.unlink()
        claim_id = uuid.uuid4().hex
        record = {"schema": LOCK_SCHEMA, "claim_id": claim_id,
                  "workspace_id": _workspace_id(), "plan_digest": plan_digest,
                  "phase": "STARTING", "created_at": now(),
                  "boot_time": float(psutil_module.boot_time()),
                  "supervisor": _process_reference(psutil_module, os.getpid()),
                  "worker": None}
        _atomic_write_lock(lock, record)
        return claim_id


def admit_inference_worker(lock: Path, claim_id: str, psutil_module) -> None:
    """Bind the owned worker before retrieval/model loading can begin."""
    lock = Path(lock)
    with _inference_gate(lock.with_name("inference.gate")):
        record = _read_lock_record(lock)
        if record.get("claim_id") != claim_id or record.get("phase") != "STARTING":
            raise ValueError("Worker does not own the active inference claim")
        try:
            current_boot = float(psutil_module.boot_time())
        except (OSError, ValueError) as exc:
            raise ValueError("Worker cannot verify host boot identity") from exc
        if abs(current_boot - float(record["boot_time"])) > 1.0:
            raise ValueError("Worker claim belongs to a prior host boot")
        if _process_reference_state(record["supervisor"], psutil_module) != "LIVE":
            raise ValueError("Worker supervisor identity is no longer live")
        record["worker"] = _process_reference(psutil_module, os.getpid())
        record["phase"] = "RUNNING"
        _atomic_write_lock(lock, record)


def release_inference_lock(lock: Path, claim_id: str, psutil_module) -> None:
    """Remove only our exact claim and only after its worker has stopped."""
    lock = Path(lock)
    with _inference_gate(lock.with_name("inference.gate")):
        record = _read_lock_record(lock)
        if record.get("claim_id") != claim_id:
            raise ValueError("Refusing to remove a replacement inference claim")
        worker = record.get("worker")
        if worker is not None:
            worker_state = _process_reference_state(worker, psutil_module)
            if worker_state != "STALE":
                raise ValueError(f"Refusing to release inference claim while worker is {worker_state}")
        released = lock.with_name(f".{lock.name}.released.{claim_id}")
        os.replace(lock, released)
        released.unlink()


def read_fixtures(args):
    from .fixtures import validate_fixtures
    corpus, queries = load_json(args.corpus), load_json(args.queries)
    audit = validate_fixtures(corpus, queries)
    if not audit["valid"]:
        raise ValueError("Fixture audit failed: " + json.dumps(audit["errors"]))
    return corpus, queries, audit


def validate_config(config):
    if config.get("schema") != DEFAULT_CONFIG["schema"]:
        raise ValueError("Unsupported configuration schema")
    for field in ("k", "chunk_tokens", "overlap_tokens", "rrf_k", "seed", "cpu_threads", "max_rss_bytes"):
        if not isinstance(config.get(field), int) or isinstance(config[field], bool):
            raise ValueError(f"{field} must be an integer")
    if not 1 <= config["k"] <= 100 or not 16 <= config["chunk_tokens"] <= 240:
        raise ValueError("k/chunk_tokens outside workbench bounds")
    if not 0 <= config["overlap_tokens"] < config["chunk_tokens"]:
        raise ValueError("Invalid chunk overlap")
    if not 1 <= config["cpu_threads"] <= 2 or not 0 < config["max_rss_bytes"] <= 2 * 1024**3:
        raise ValueError("Resource limits exceed authorized CPU/RSS ceiling")
    if config["rrf_k"] < 1:
        raise ValueError("rrf_k must be positive")
    for field in ("lexical_weight", "semantic_weight"):
        value = config.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{field} must be finite and positive")
    return config


def portable_diagnostic(value, selected_artifacts=None):
    """Keep diagnostic meaning while omitting machine-specific absolute paths."""
    text = str(value)
    replacements = [(str(artifact_root(selected_artifacts)), "<ARTIFACTS>"),
                    (str(ROOT.resolve()), "<WORKBENCH>"),
                    (str(Path(sys.executable).resolve().parent), "<PYTHON>")]
    for original, label in sorted(replacements, key=lambda pair: -len(pair[0])):
        text = text.replace(original, label).replace(original.replace("\\", "/"), label)
    text = re.sub(r"[A-Za-z]:[\\/][^\n\r\"']+", "<ABSOLUTE_PATH>", text)
    return text


def reproduction_configuration():
    config = deepcopy(DEFAULT_CONFIG)
    config["id"] = "chunk240-lex1-rrf60"
    return config


def prepare_reproduction(args):
    """Declare a previously selected protocol; this performs no new selection."""
    from .retrieval import MODEL_SPECS
    corpus, queries, _ = read_fixtures(args)
    current = source_identity(args.artifacts)
    config = reproduction_configuration()
    manifest = {"schema": "hippo-eval-reproduction/v1", "created_at": now(),
                "mode": "known_split_reproduction", "selection_performed": False,
                "original_heldout_already_known": True,
                "configuration_origin": "previously_selected_fixed_configuration",
                "fixture_digest": digest({"corpus": corpus, "queries": queries}),
                "source_digest": current["source_digest"],
                "dependency_digest": current["dependency_digest"],
                "configuration": config, "configuration_digest": digest(config),
                "model_specs": deepcopy(MODEL_SPECS)}
    if Path(args.out).exists():
        raise ValueError("Reproduction declaration already exists; preserve prior evidence")
    write_json(args.out, manifest)
    return manifest


def validated_reproduction(args, corpus, queries):
    from .retrieval import MODEL_SPECS
    manifest = load_json(args.reproduction)
    if (manifest.get("schema") != "hippo-eval-reproduction/v1"
            or manifest.get("mode") != "known_split_reproduction"
            or manifest.get("selection_performed") is not False
            or manifest.get("original_heldout_already_known") is not True
            or manifest.get("configuration_origin") != "previously_selected_fixed_configuration"):
        raise ValueError("Invalid known-split reproduction declaration")
    if manifest.get("fixture_digest") != digest({"corpus": corpus, "queries": queries}):
        raise ValueError("Reproduction fixture identity differs")
    current = source_identity(args.artifacts)
    for key in ("source_digest", "dependency_digest"):
        if manifest.get(key) != current[key]:
            raise ValueError(f"Reproduction {key} differs from current identity")
    config = reproduction_configuration()
    if manifest.get("configuration") != config or manifest.get("configuration_digest") != digest(config):
        raise ValueError("Reproduction configuration differs from the fixed historical protocol")
    if manifest.get("model_specs") != MODEL_SPECS:
        raise ValueError("Reproduction model specifications differ")
    return manifest


def config_for(args, corpus, queries):
    if getattr(args, "reproduction", None):
        if args.config or args.frozen:
            raise ValueError("--reproduction, --config and --frozen are mutually exclusive")
        return validate_config(validated_reproduction(args, corpus, queries)["configuration"])
    config = deepcopy(DEFAULT_CONFIG) if not args.config else load_json(args.config)
    if args.frozen:
        frozen = load_json(args.frozen)
        if frozen.get("schema") != "hippo-eval-freeze/v1" or frozen.get("holdout_used") is not False:
            raise ValueError("Invalid development-only freeze")
        if frozen["fixture_digest"] != digest({"corpus": corpus, "queries": queries}):
            raise ValueError("Freeze fixture identity differs")
        config = frozen["configuration"]
        if frozen["configuration_digest"] != digest(config):
            raise ValueError("Freeze configuration digest differs")
        current = source_identity(args.artifacts)
        if frozen["dependency_digest"] != current["dependency_digest"]:
            raise ValueError("Dependencies changed since freeze")
        if frozen["source_digest"] != current["source_digest"]:
            raise ValueError("Source changed since freeze; perform development comparison again")
        if args.config:
            raise ValueError("--config and --frozen are mutually exclusive")
    elif args.split == "heldout":
        raise ValueError("Held-out execution requires --frozen from development comparison")
    return validate_config(config)


def observe_hit(engine, hit, expected, query):
    """Hash observed full fetch, never expected payloads, into result evidence."""
    hit = dict(hit)
    actual = engine.fetch(hit["record_id"])
    issues = []
    if not isinstance(actual, dict):
        raise ValueError("Adapter fetch did not return a record object")
    expected_record = expected.get(hit["record_id"])
    if expected_record is None:
        issues.append("UNKNOWN_RECORD_ID")
    else:
        if actual.get("id") != hit["record_id"]:
            issues.append("FETCH_ID_MISMATCH")
        if actual.get("body") != expected_record.get("body"):
            issues.append("FULL_BODY_MISMATCH")
        if actual.get("provenance") != expected_record.get("provenance"):
            issues.append("PROVENANCE_MISMATCH")
        if digest(actual) != digest(expected_record):
            issues.append("FULL_RECORD_MISMATCH")
        if not eligible(actual, query):
            issues.append("OBSERVED_INELIGIBLE")
    hit["body_sha256"] = body_digest(actual.get("body"))
    hit["record_sha256"] = digest(actual)
    hit["provenance_sha256"] = digest(actual.get("provenance"))
    hit["observed"] = {key: actual.get(key) for key in
                       ("project", "task", "owner", "status", "epistemic", "revision")}
    hit["fidelity"] = {"passed": not issues, "issues": issues}
    return hit


def evaluate(args, semantic_blocker=None):
    from .retrieval import create_engine, RetrievalMissing
    from .metrics import score_bundle
    from .reporting import write_reports
    corpus, queries, audit = read_fixtures(args)
    config = config_for(args, corpus, queries)
    names = parse_methods(args.methods)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "run.json").exists() or (out / "run.partial.json").exists():
        raise ValueError("Output already contains evidence; choose a new --out")
    identity = source_identity(args.artifacts)
    identity["fixture_digest"] = digest({"corpus": corpus, "queries": queries})
    selected = [q for q in queries["queries"] if q["split"] == args.split]
    if not selected:
        raise ValueError("Requested split contains no queries")
    bundle = {"schema": RUN_SCHEMA, "run_id": uuid.uuid4().hex, "created_at": now(),
              "execution": "executed_local_synthetic", "split": args.split,
              "identity": identity, "configuration": config,
              "configuration_digest": digest(config), "methods": [],
              "integrity_errors": [], "fixture_audit": audit,
              "execution_runtime": {"pid": os.getpid(), "isolated": bool(sys.flags.isolated),
                                    "no_site": bool(sys.flags.no_site),
                                    "executable_name": Path(sys.executable).name,
                                    "artifact_site": "<ARTIFACTS>/site"},
              "product_execution": "NOT_RUN"}
    if getattr(args, "reproduction", None):
        bundle["reproduction"] = validated_reproduction(args, corpus, queries)
    expected = {r["id"]: r for r in corpus["records"]}
    write_json(out / "run.partial.json", bundle)
    for name in names:
        print(f"METHOD_START {name}", flush=True)
        engine = None
        result = {"name": name, "status": "NOT_RUN", "identity": {"requested": name},
                  "configuration_digest": digest(config), "measurements":
                  {"load_ms": None, "index_ms": None, "query_latency_ms": []},
                  "errors": [], "queries": []}
        try:
            if semantic_blocker and name != "lexical":
                raise FileNotFoundError(semantic_blocker)
            engine = create_engine(name, artifact_root=Path(args.artifacts))
            result["measurements"].update(engine.build(corpus["records"], config))
            result["identity"] = deepcopy(engine.identity)
            if args.frozen and result["identity"] != load_json(args.frozen)["method_identities"].get(name):
                raise ValueError("Model/adapter identity changed since development freeze")
            result["status"] = "EXECUTED"
            for query in selected:
                started = time.perf_counter()
                observation = {"query_id": query["id"], "status": "OK", "ranked": [], "errors": []}
                try:
                    allowed = {rid for rid, record in expected.items() if eligible(record, query)}
                    hits = engine.search(query, allowed, config["k"])
                    observation["ranked"] = [observe_hit(engine, hit, expected, query) for hit in hits]
                except Exception as exc:
                    observation["status"] = "ERROR"
                    observation["errors"] = [portable_diagnostic(f"{type(exc).__name__}: {exc}", getattr(args, "artifacts", None))]
                observation["elapsed_ms"] = (time.perf_counter() - started) * 1000
                result["queries"].append(observation)
                result["measurements"]["query_latency_ms"].append(observation["elapsed_ms"])
        except (FileNotFoundError, ImportError, RetrievalMissing) as exc:
            result["status"] = "NOT_RUN"
            result["errors"].append(portable_diagnostic(f"{type(exc).__name__}: {exc}", getattr(args, "artifacts", None)))
        except Exception as exc:
            result["status"] = "FAILED"
            result["errors"].append(portable_diagnostic(f"{type(exc).__name__}: {exc}", getattr(args, "artifacts", None)))
        finally:
            if engine is not None:
                try:
                    engine.close()
                except Exception as exc:
                    result["status"] = "FAILED"
                    result["errors"].append(portable_diagnostic(f"Close failed: {type(exc).__name__}: {exc}", args.artifacts))
        bundle["methods"].append(result)
        write_json(out / "run.partial.json", bundle)
        print(f"METHOD_END {name} {result['status']}", flush=True)
    if getattr(args, "reproduction", None):
        if load_json(args.reproduction) != bundle["reproduction"]:
            bundle["integrity_errors"].append("REPRODUCTION_DECLARATION_CHANGED_DURING_RUN")
    if getattr(args, "reproduction", None):
        if load_json(args.reproduction) != bundle["reproduction"]:
            bundle["integrity_errors"].append("REPRODUCTION_DECLARATION_CHANGED_DURING_RUN")
    after = source_identity(args.artifacts)
    if after["source_digest"] != identity["source_digest"]:
        bundle["integrity_errors"].append("SOURCE_CHANGED_DURING_RUN")
    if after["dependency_digest"] != identity["dependency_digest"]:
        bundle["integrity_errors"].append("DEPENDENCIES_CHANGED_DURING_RUN")
    if digest({"corpus": load_json(args.corpus), "queries": load_json(args.queries)}) != identity["fixture_digest"]:
        bundle["integrity_errors"].append("FIXTURES_CHANGED_DURING_RUN")
    analysis = score_bundle(bundle, corpus, queries)
    bundle["analysis"] = analysis
    output_name = "worker-result.json" if getattr(args, "worker", False) else "run.json"
    bundle["supervision_state"] = "PENDING" if getattr(args, "worker", False) else "UNSUPERVISED_LEXICAL_ONLY"
    write_json(out / output_name, bundle)
    if output_name == "run.json":
        write_json(out / "run.json.gz", bundle)
    write_json(out / "analysis.json", analysis)
    write_reports(bundle, analysis, out)
    # Worker process completion and method outcomes are different facts. A
    # truthful NOT_RUN/FAILED method still permits the supervisor to publish
    # independent successful methods with a valid resource receipt.
    if getattr(args, "worker", False):
        return 0 if analysis["valid"] else 1
    return 0 if experiment_succeeded(bundle) else 1


def experiment_succeeded(bundle):
    return bool(bundle.get("analysis", {}).get("valid")) and bool(bundle.get("methods")) and all(
        method.get("status") == "EXECUTED" and all(query.get("status") == "OK" for query in method.get("queries", []))
        for method in bundle["methods"])


def parse_methods(value):
    names = value.split(",")
    if not names or any(name not in METHODS for name in names):
        raise ValueError("Methods must be a comma-separated selection of " + ",".join(METHODS))
    if len(names) != len(set(names)):
        raise ValueError("Duplicate method names are not permitted")
    return names


def declared_configs():
    configs = []
    for chunk in (128, 240):
        for weight in (1.0, 2.0):
            config = deepcopy(DEFAULT_CONFIG)
            config.update(id=f"chunk{chunk}-lex{int(weight)}-rrf60", chunk_tokens=chunk,
                          lexical_weight=weight)
            configs.append(config)
    return configs


def select_development(bundles):
    """Predeclared selection, with no held-out access or label modifications."""
    if len(bundles) != 4:
        raise ValueError("Selection requires all four declared development runs")
    expected = {digest(c) for c in declared_configs()}
    seen, identities, model_identities, rows = set(), set(), set(), []
    for bundle in bundles:
        if bundle.get("split") != "development":
            raise ValueError("Selection cannot consume held-out runs")
        identity = bundle["identity"]
        identities.add((identity["source_digest"], identity["fixture_digest"],
                        identity["dependency_digest"], identity["metric_version"]))
        cfg_digest = bundle["configuration_digest"]
        if cfg_digest != digest(bundle["configuration"]) or cfg_digest not in expected or cfg_digest in seen:
            raise ValueError("Unexpected, duplicate, or tampered development configuration")
        seen.add(cfg_digest)
        analysis = bundle["analysis"]
        if not analysis.get("valid"):
            raise ValueError("Invalid development run cannot select a winner")
        if bundle.get("supervision_required") is not True or bundle.get("supervision_state") != "COMPLETED":
            raise ValueError("Development selection requires completed, validated supervision")
        model_identities.add(digest({m["name"]: m["identity"] for m in bundle["methods"]}))
        methods = {m["name"]: m for m in analysis["methods"]}
        if set(methods) != set(METHODS) or any(m["status"] != "EXECUTED" or not m["valid"] for m in methods.values()):
            raise ValueError("All five methods must execute validly before semantic selection")
        selected_methods = [methods[name] for name in METHODS if name != "lexical"]
        if any(m["summary"]["error_queries"] or m["summary"]["unavailable_queries"] for m in selected_methods):
            raise ValueError("Failed queries prevent semantic selection")
        scores = [m["summary"]["ndcg_at_k"] for m in selected_methods]
        if any(not isinstance(v, (float, int)) or not math.isfinite(v) for v in scores):
            raise ValueError("Selection requires finite answerable-query nDCG")
        chunks = sum(m["measurements"]["indexed_chunks"] for m in bundle["methods"] if m["name"] in ("bge", "minilm"))
        rows.append({"run_id": bundle["run_id"], "configuration": bundle["configuration"],
                     "configuration_digest": cfg_digest, "mean_ndcg_at_k": sum(scores) / len(scores),
                     "indexed_semantic_chunks": chunks})
    if len(identities) != 1:
        raise ValueError("Source/fixtures/dependencies/metric changed between development runs")
    if len(model_identities) != 1:
        raise ValueError("Model/adapter identities changed between development runs")
    best = max(row["mean_ndcg_at_k"] for row in rows)
    tied = [row for row in rows if best - row["mean_ndcg_at_k"] <= .005]
    chosen = min(tied, key=lambda row: (row["indexed_semantic_chunks"],
                                      row["configuration"]["lexical_weight"], row["configuration_digest"]))
    return {"schema": "hippo-eval-development-comparison/v1", "holdout_used": False,
            "selection_rule": "mean answerable development nDCG@10 of four semantic/hybrid methods; within .005 prefer fewer semantic chunks then lexical weight 1",
            "candidates": rows, "selected": chosen}


def freeze_from_bundles(bundles, out, corpus, queries, selected_artifacts=None):
    from .metrics import score_bundle
    # Embedded analyses are convenient reports, never the source of truth.
    bundles = deepcopy(bundles)
    for bundle in bundles:
        bundle["analysis"] = score_bundle(bundle, corpus, queries)
    comparison = select_development(bundles)
    selected = next(b for b in bundles if b["run_id"] == comparison["selected"]["run_id"])
    identity = selected["identity"]
    current = source_identity(selected_artifacts)
    if any(identity[key] != current[key] for key in ("source_digest", "dependency_digest")):
        raise ValueError("Cannot freeze stale source/dependency evidence")
    frozen = {"schema": "hippo-eval-freeze/v1", "created_at": now(), "holdout_used": False,
              "fixture_digest": identity["fixture_digest"], "source_digest": identity["source_digest"],
              "dependency_digest": identity["dependency_digest"],
              "configuration": selected["configuration"],
              "configuration_digest": selected["configuration_digest"],
              "development_run_ids": [b["run_id"] for b in bundles],
              "method_identities": {m["name"]: m["identity"] for m in selected["methods"]},
              "selection": comparison}
    if Path(out).exists():
        raise ValueError("Freeze output already exists; preserve prior evidence")
    write_json(out, frozen)
    return frozen


def compare_configurations(args):
    corpus, queries, _ = read_fixtures(args)
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Development comparison output must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "declared.json", {"created_at": now(), "holdout_used": False,
               "identity": source_identity(args.artifacts), "fixture_digest": digest({"corpus": corpus, "queries": queries}),
               "configurations": declared_configs()})
    bundles = []
    for config in declared_configs():
        config_path = out / (config["id"] + ".json")
        write_json(config_path, config)
        run_args = argparse.Namespace(**vars(args))
        run_args.config, run_args.frozen, run_args.split = config_path, None, "development"
        run_args.methods = ",".join(METHODS)
        run_args.out = out / config["id"]
        code = supervised_run(run_args)
        if code:
            write_json(out / "selection-pending.json", {"status": "NOT_SELECTED",
                       "reason": "Development candidate did not complete validly; no semantic winner claimed",
                       "failed_configuration": config["id"], "exit_code": code})
            return 1
        bundles.append(load_json(run_args.out / "run.json"))
    frozen = freeze_from_bundles(bundles, out / "frozen.json", corpus, queries, args.artifacts)
    write_json(out / "comparison.json", frozen["selection"])
    print(f"Selected {frozen['configuration']['id']}; freeze: {out / 'frozen.json'}")
    return 0


def supervised_run(args):
    """Monitor only our owned child; never enumerate unrelated processes."""
    selected_artifacts = artifact_root(args.artifacts)
    bootstrap_artifact_site(selected_artifacts)
    parse_methods(args.methods)
    corpus, queries, _ = read_fixtures(args)
    config = config_for(args, corpus, queries)
    try:
        import psutil
    except ImportError:
        return evaluate(args, semantic_blocker="psutil is required for semantic RSS monitoring; model NOT RUN")
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Output directory must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    plan_identity = source_identity(selected_artifacts)
    plan_identity["fixture_digest"] = digest({"corpus": corpus, "queries": queries})
    execution_plan = {"schema": "hippo-eval-execution-plan/v1",
                      "created_at": now(), "identity": plan_identity, "split": args.split,
                      "configuration": config, "configuration_digest": digest(config),
                      "methods": parse_methods(args.methods), "max_seconds": args.max_seconds,
                      "product_execution": "NOT_RUN"}
    if getattr(args, "reproduction", None):
        execution_plan["reproduction"] = validated_reproduction(args, corpus, queries)
    if getattr(args, "reproduction", None):
        execution_plan["reproduction"] = validated_reproduction(args, corpus, queries)
    write_json(out / "execution-plan.json", execution_plan)
    lock_dir = ROOT / ".scratch"
    lock_dir.mkdir(exist_ok=True)
    lock = lock_dir / "inference.lock"
    claim_id = acquire_inference_lock(lock, psutil, digest(execution_plan))
    proc = None
    try:
        # Windows venv python.exe can be a launcher whose RSS excludes the actual
        # interpreter. Start this interpreter's known base executable directly,
        # disable site initialization, then bootstrap only the selected site.
        base_executable = str(Path(getattr(sys, "_base_executable", sys.executable)).resolve())
        cmd = [base_executable, "-I", "-S", str(ROOT / "workbench.py"), "run", "--worker",
               "--claim-id", claim_id, "--corpus", str(args.corpus),
               "--queries", str(args.queries), "--split", args.split,
               "--methods", args.methods, "--out", str(out),
               "--artifacts", str(selected_artifacts)]
        if getattr(args, "reproduction", None):
            cmd += ["--reproduction", str(args.reproduction)]
        if args.config:
            cmd += ["--config", str(args.config)]
        if args.frozen:
            cmd += ["--frozen", str(args.frozen)]
        started, peak, samples, reason = time.perf_counter(), 0, 0, None
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS="2", MKL_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2",
                   TOKENIZERS_PARALLELISM="false", CUDA_VISIBLE_DEVICES="",
                   HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   HF_HUB_DISABLE_IMPLICIT_TOKEN="1", HF_HUB_DISABLE_TELEMETRY="1",
                   HF_HOME=str(selected_artifacts / "hf-cache"),
                   TORCH_HOME=str(selected_artifacts / "torch-cache"),
                   XDG_CACHE_HOME=str(selected_artifacts / "cache"))
        log_path = out / "execution.txt"
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, env=env,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            monitor = psutil.Process(proc.pid)
            while proc.poll() is None:
                try:
                    rss = monitor.memory_info().rss
                    peak = max(peak, rss)
                    samples += 1
                    if rss > config["max_rss_bytes"]:
                        reason = "INFERENCE_RSS_LIMIT_EXCEEDED"
                    elif time.perf_counter() - started > args.max_seconds:
                        reason = "RUN_TIME_LIMIT_EXCEEDED"
                    if reason:
                        proc.kill()
                        break
                except psutil.NoSuchProcess:
                    break
                time.sleep(0.1)
            code = proc.wait(timeout=10)
        resource = {"peak_rss_bytes": peak, "rss_samples": samples, "sample_interval_ms": 100,
                    "elapsed_ms": (time.perf_counter() - started) * 1000,
                    "limit_bytes": config["max_rss_bytes"], "failure": reason,
                    "child_exit_code": code, "monitored_pid": proc.pid,
                    "scope": "direct_base_interpreter_owned_inference_process_only",
                    "guard": "100ms sampled RSS watchdog; not an OS hard allocation limit"}
        write_json(out / "resource.json", resource)
        if reason or not (out / "worker-result.json").exists():
            write_json(out / "failure.json", {"status": "FAILED", "reason": reason or "CHILD_FAILED",
                                               "resource": resource, "product_execution": "NOT_RUN"})
            if (out / "run.partial.json").exists():
                write_json(out / "partial.json.gz", load_json(out / "run.partial.json"))
            print(f"Run failed; retained {out / 'failure.json'}")
            return 1
        from .reporting import write_reports
        bundle = load_json(out / "worker-result.json")
        if bundle.get("execution_runtime", {}).get("pid") != proc.pid:
            resource["failure"] = "MONITORED_PID_DIFFERS_FROM_WORKER"
            bundle["integrity_errors"].append("MONITORED_PID_DIFFERS_FROM_WORKER")
            code = 1
        bundle["resource"] = resource
        bundle["supervision_required"] = True
        bundle["supervision_state"] = "COMPLETED"
        for method in bundle["methods"]:
            method["measurements"]["supervisor_peak_rss_bytes"] = peak
        from .metrics import score_bundle
        bundle["analysis"] = score_bundle(bundle, corpus, queries)
        if not experiment_succeeded(bundle):
            code = 1
        write_json(out / "resource.json", resource)
        write_json(out / "run.json", bundle)
        write_json(out / "run.json.gz", bundle)
        write_json(out / "analysis.json", bundle["analysis"])
        write_reports(bundle, bundle["analysis"], out)
        print(f"Run {out}: exit={code}, peak RSS={peak / 1024**2:.1f} MiB")
        return code
    finally:
        try:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
        finally:
            release_inference_lock(lock, claim_id, psutil)


def _test_source_files(pattern: str) -> dict:
    test_root = ROOT / "tests"
    if not test_root.is_dir():
        return {}
    matched = []
    pending = [test_root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            if path.is_dir() and (path / "__init__.py").is_file():
                pending.append(path)
            elif path.is_file() and fnmatch.fnmatch(path.name, pattern):
                matched.append(path)
    return {str(path.relative_to(test_root)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(matched)}


class SmokeTestResult(unittest.TextTestResult):
    """Count skipped test methods without subtracting fixture-level skips."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_tests = []
        self.started_skips = 0

    def startTest(self, test):
        self.started_tests.append(test)
        super().startTest(test)

    def addSkip(self, test, reason):
        if any(test is started for started in self.started_tests):
            self.started_skips += 1
        super().addSkip(test, reason)


def run_smoke(args) -> int:
    started = time.perf_counter()
    before = source_identity()
    tests = _test_source_files(args.pattern)
    stream = io.StringIO()
    suite = outcome = None
    discovery_error = None
    try:
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern=args.pattern)
        tests_discovered = suite.countTestCases()
        outcome = unittest.TextTestRunner(stream=stream, verbosity=2,
                                          resultclass=SmokeTestResult).run(suite)
    except Exception as exc:
        tests_discovered = 0
        discovery_error = portable_diagnostic(f"{type(exc).__name__}: {exc}", getattr(args, "artifacts", None))
    output = portable_diagnostic(stream.getvalue())
    if discovery_error:
        output += f"Discovery failed: {discovery_error}\n"
    after_tests = _test_source_files(args.pattern)
    unchanged = source_identity() == before and tests == after_tests
    tests_run = outcome.testsRun if outcome is not None else 0
    skipped = len(outcome.skipped) if outcome is not None else 0
    failures = len(outcome.failures) if outcome is not None else 0
    errors = len(outcome.errors) if outcome is not None else 0
    tests_executed = max(0, tests_run - getattr(outcome, "started_skips", 0))
    if discovery_error:
        status, failure_reason = "DISCOVERY_FAILED", "DISCOVERY_ERROR"
    elif not tests:
        status, failure_reason = "DISCOVERY_FAILED", "NO_TEST_FILES_DISCOVERED"
    elif tests_discovered == 0:
        status, failure_reason = "DISCOVERY_FAILED", "NO_TEST_CASES_DISCOVERED"
    elif not outcome.wasSuccessful():
        status, failure_reason = "TEST_FAILURES", "TESTS_FAILED"
    elif tests_executed == 0:
        status, failure_reason = "ZERO_TESTS_EXECUTED", "NO_TESTS_EXECUTED"
    elif not unchanged:
        status, failure_reason = "SOURCE_CHANGED", "SOURCE_OR_TESTS_CHANGED"
    else:
        status, failure_reason = "PASSED", None
    receipt = {"schema": "hippo-eval-test-receipt/v2", "created_at": now(),
               "passed": status == "PASSED", "status": status,
               "failure_reason": failure_reason, "pattern": args.pattern,
               "source_unchanged": unchanged, "test_files_discovered": len(tests),
               "tests_discovered": tests_discovered, "tests_run": tests_run,
               "tests_executed": tests_executed, "skipped": skipped,
               "failures": failures, "errors": errors,
               "discovery_error": discovery_error,
               "elapsed_ms": (time.perf_counter() - started) * 1000,
               "identity": before, "test_source_files": tests,
               "output": output,
               "scope": "evaluator and experimental adapter tests; product execution NOT RUN"}
    if output:
        print(output)
    print(json.dumps({key: receipt[key] for key in
                      ("passed", "status", "failure_reason", "test_files_discovered",
                       "tests_discovered", "tests_run", "tests_executed",
                       "failures", "errors")}, indent=2))
    if args.out:
        write_json(args.out, receipt)
    return 0 if receipt["passed"] else 1


def add_fixture_arguments(parser):
    parser.add_argument("--corpus", type=Path, default=ROOT / "fixtures" / "corpus.json")
    parser.add_argument("--queries", type=Path, default=ROOT / "fixtures" / "queries.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reproducible Retrieval Evaluation",
                                     allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Audit corpus and relevance fixtures", allow_abbrev=False)
    add_fixture_arguments(validate)
    validate.add_argument("--out", type=Path)
    smoke = sub.add_parser("smoke", help="Run evaluator/adapter unit and integration tests", allow_abbrev=False)
    smoke.add_argument("--pattern", default="test_*.py")
    smoke.add_argument("--out", type=Path)
    run = sub.add_parser("run", help="Execute retrieval and report observed results", allow_abbrev=False)
    add_fixture_arguments(run)
    run.add_argument("--split", choices=("development", "heldout"), default="development")
    run.add_argument("--methods", default=",".join(METHODS))
    run.add_argument("--config", type=Path)
    run.add_argument("--frozen", type=Path)
    run.add_argument("--reproduction", type=Path, help="Explicit known-split reproduction declaration")
    run.add_argument("--artifacts", type=Path, default=ROOT / ".artifacts")
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--max-seconds", type=int, default=900)
    run.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    run.add_argument("--claim-id", help=argparse.SUPPRESS)
    reproduction = sub.add_parser("prepare-reproduction", help="Declare the fixed historical protocol without new selection", allow_abbrev=False)
    add_fixture_arguments(reproduction)
    reproduction.add_argument("--artifacts", type=Path, default=ROOT / ".artifacts")
    reproduction.add_argument("--out", type=Path, required=True)
    development = sub.add_parser("compare-configs", help="Execute declared development grid and freeze selection",
                                 allow_abbrev=False)
    add_fixture_arguments(development)
    development.add_argument("--artifacts", type=Path, default=ROOT / ".artifacts")
    development.add_argument("--out", type=Path, required=True)
    development.add_argument("--max-seconds", type=int, default=900)
    freeze = sub.add_parser("freeze", help="Select/freeze four already executed development runs", allow_abbrev=False)
    add_fixture_arguments(freeze)
    freeze.add_argument("bundles", type=Path, nargs=4)
    freeze.add_argument("--artifacts", type=Path, default=ROOT / ".artifacts")
    freeze.add_argument("--out", type=Path, required=True)
    score = sub.add_parser("score", help="Validate and score an externally supplied result bundle", allow_abbrev=False)
    add_fixture_arguments(score)
    score.add_argument("bundle", type=Path)
    score.add_argument("--out", type=Path, required=True)
    compare = sub.add_parser("compare", help="Compare two compatible scored runs", allow_abbrev=False)
    add_fixture_arguments(compare)
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--out", type=Path, required=True)
    compare.add_argument("--report-out", type=Path)
    report = sub.add_parser("report", help="Render saved run analysis to Markdown and static HTML", allow_abbrev=False)
    add_fixture_arguments(report)
    report.add_argument("bundle", type=Path)
    report.add_argument("--out", type=Path, required=True)
    scenario = sub.add_parser("check-traces", help="Check supplied synthetic/product observation traces",
                              allow_abbrev=False)
    scenario.add_argument("scenarios", type=Path)
    scenario.add_argument("traces", type=Path)
    scenario.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if hasattr(args, "artifacts"):
        args.artifacts = artifact_root(args.artifacts)
        bootstrap_artifact_site(args.artifacts)
    try:
        if args.command == "validate":
            from .fixtures import validate_fixtures
            audit = validate_fixtures(load_json(args.corpus), load_json(args.queries))
            if args.out:
                write_json(args.out, audit)
            display = {"valid": audit["valid"], "records": audit["summary"].get("record_count"),
                       "queries": audit["summary"].get("query_count"), "errors": audit["errors"],
                       "warnings": audit["warnings"], "output": str(args.out)} if args.out else audit
            print(json.dumps(display, indent=2))
            return 0 if audit["valid"] else 1
        if args.command == "smoke":
            return run_smoke(args)
        if args.command == "run":
            if args.max_seconds < 1 or args.max_seconds > 3600:
                raise ValueError("max-seconds must be between 1 and 3600")
            if args.worker:
                if not args.claim_id:
                    raise ValueError("An isolated worker requires an active inference claim")
                try:
                    import psutil
                except ImportError as exc:
                    raise ImportError("psutil is required to admit the isolated worker") from exc
                admit_inference_worker(ROOT / ".scratch" / "inference.lock",
                                       args.claim_id, psutil)
                return evaluate(args)
            return supervised_run(args)
        if args.command == "prepare-reproduction":
            prepare_reproduction(args)
            return 0
        if args.command == "compare-configs":
            if args.max_seconds < 1 or args.max_seconds > 3600:
                raise ValueError("max-seconds must be between 1 and 3600")
            return compare_configurations(args)
        if args.command == "freeze":
            corpus, queries, _ = read_fixtures(args)
            frozen = freeze_from_bundles([load_json(p) for p in args.bundles], args.out,
                                         corpus, queries, args.artifacts)
            print(json.dumps(frozen["selection"], indent=2))
            return 0
        if args.command == "score":
            from .metrics import score_bundle
            from .reporting import write_reports
            corpus, queries, _ = read_fixtures(args)
            bundle = load_json(args.bundle)
            analysis = score_bundle(bundle, corpus, queries)
            write_json(args.out / "analysis.json", analysis)
            write_reports(bundle, analysis, args.out)
            return 0 if analysis["valid"] else 1
        if args.command == "compare":
            from .metrics import compare_runs, score_bundle
            from .reporting import write_reports
            corpus, queries, _ = read_fixtures(args)
            before, after = load_json(args.before), load_json(args.after)
            before_analysis = score_bundle(before, corpus, queries)
            after_analysis = score_bundle(after, corpus, queries)
            result = compare_runs(before_analysis, after_analysis)
            write_json(args.out, result)
            if args.report_out:
                write_reports(after, after_analysis, args.report_out, result)
            print(json.dumps({"compatible": result.get("compatible"), "regressed": result.get("regressed"),
                              "reasons": result.get("reasons"), "output": str(args.out)}, indent=2))
            return 0 if (result.get("compatible") is True
                         and result.get("regressed") is False) else 1
        if args.command == "report":
            from .reporting import write_reports
            from .metrics import score_bundle
            corpus, queries, _ = read_fixtures(args)
            bundle = load_json(args.bundle)
            analysis = score_bundle(bundle, corpus, queries)
            write_reports(bundle, analysis, args.out)
            return 0 if analysis["valid"] else 1
        if args.command == "check-traces":
            from .scenarios import check_traces
            scenarios, traces = load_json(args.scenarios), load_json(args.traces)
            result = check_traces(scenarios, traces)
            result.update(identity=source_identity(), created_at=now(),
                          scenario_digest=digest(scenarios), trace_digest=digest(traces))
            if args.out:
                write_json(args.out, result)
            display = {"valid": result["valid"], "summary": result.get("summary"),
                       "failed_cases": [case["id"] for case in result.get("cases", []) if not case.get("passed")],
                       "output": str(args.out), "product_execution": result.get("product_execution")} if args.out else result
            print(json.dumps(display, indent=2))
            return 0 if result["valid"] else 1
    except (ValueError, KeyError, OSError, ImportError, TypeError) as exc:
        print(portable_diagnostic(f"{type(exc).__name__}: {exc}", getattr(args, "artifacts", None)), file=sys.stderr)
        return 2
    return 2
