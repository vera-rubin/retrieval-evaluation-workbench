"""Bounded public, hash-locked Windows CPython313 CPU staging only.

Downloads selected wheels and immutable model files, never a broad HF snapshot.
No credentials, provider calls, custom model code, source builds, or inference.
"""
from __future__ import annotations
import argparse
import email
import hashlib
import html
import json
import platform
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

from pip._vendor.packaging.markers import default_environment
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import canonicalize_name, parse_wheel_filename
from pip._vendor.packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts"
RECEIPTS = ARTIFACTS / "receipts"
MAX_BYTES = 3 * 1024**3
PINS = {
    "apsw": "3.53.4.0", "sqlite-vec": "0.1.9", "torch": "2.9.1+cpu",
    "transformers": "4.57.1", "tokenizers": "0.22.1", "safetensors": "0.6.2",
    "huggingface-hub": "0.36.0", "hf-xet": "1.2.0", "numpy": "2.3.4",
    "filelock": "3.19.1", "fsspec": "2025.9.0", "packaging": "25.0",
    "pyyaml": "6.0.3", "regex": "2025.9.18", "requests": "2.32.5",
    "tqdm": "4.67.1", "typing-extensions": "4.15.0", "jinja2": "3.1.6",
    "markupsafe": "3.0.3", "networkx": "3.5", "sympy": "1.14.0",
    "mpmath": "1.3.0", "charset-normalizer": "3.4.4", "idna": "3.11",
    "urllib3": "2.5.0", "certifi": "2025.10.5", "colorama": "0.4.6",
    "setuptools": "80.9.0", "psutil": "7.1.0",
}
MODELS = {
    "bge": ("BAAI/bge-small-en-v1.5", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"),
    "minilm": ("sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"),
}
ALLOW_FILES = {"model.safetensors", "config.json", "tokenizer.json", "tokenizer_config.json",
               "special_tokens_map.json", "vocab.txt", "README.md", "LICENSE", "LICENSE.txt",
               "NOTICE", "NOTICE.txt", "modules.json", "1_Pooling/config.json",
               "sentence_bert_config.json", "config_sentence_transformers.json"}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024**2), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_bytes():
    return sum(path.stat().st_size for path in ARTIFACTS.rglob("*") if path.is_file())


def allowed(url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (
        host in {"pypi.org", "files.pythonhosted.org", "download.pytorch.org", "download-r2.pytorch.org", "huggingface.co"}
        or host.endswith(".huggingface.co") or host.endswith(".hf.co") or host.endswith(".xethub.hf.co"))


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise RuntimeError("Unapproved public download redirect host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(Redirect)


def request(url):
    if not allowed(url):
        raise RuntimeError("Unexpected public download host: " + str(urllib.parse.urlparse(url).hostname))
    return OPENER.open(urllib.request.Request(url, headers={"User-Agent": "retrieval-evaluation-workbench-staging/1"}), timeout=60)


def get_json(url):
    with request(url) as response:
        return json.load(response)


def download(url, path, expected_sha=None, expected_bytes=None):
    if path.exists():
        actual = sha(path)
        if expected_sha and actual != expected_sha:
            raise RuntimeError(f"Existing artifact hash mismatch: {path.name}")
        if expected_bytes is not None and path.stat().st_size != expected_bytes:
            raise RuntimeError(f"Existing artifact size mismatch: {path.name}")
        return actual
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    h = hashlib.sha256()
    count = 0
    initial = artifact_bytes()
    started = time.monotonic()
    with request(url) as response, partial.open("wb") as output:
        for chunk in iter(lambda: response.read(1024**2), b""):
            count += len(chunk)
            if initial + count > MAX_BYTES:
                raise RuntimeError("STAGING_SIZE_LIMIT")
            if time.monotonic() - started > 600:
                raise TimeoutError("Single artifact exceeded ten-minute download bound")
            h.update(chunk)
            output.write(chunk)
    actual = h.hexdigest()
    if expected_sha and actual != expected_sha:
        raise RuntimeError("Downloaded artifact SHA256 mismatch")
    if expected_bytes is not None and count != expected_bytes:
        raise RuntimeError("Downloaded artifact size mismatch")
    partial.replace(path)
    return actual


def resolve_wheel(name, version):
    tags = {tag: rank for rank, tag in enumerate(sys_tags())}
    choices = []
    if name == "torch":
        with request("https://download.pytorch.org/whl/cpu/torch/") as response:
            text = response.read().decode()
        for found in re.finditer(r'href="([^"]+)"', text):
            link = urllib.parse.urljoin("https://download.pytorch.org/whl/cpu/torch/", html.unescape(found.group(1)))
            parsed = urllib.parse.urlparse(link)
            filename = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
            if filename != f"torch-{version}-cp313-cp313-win_amd64.whl":
                continue
            filehash = urllib.parse.parse_qs(parsed.fragment).get("sha256", [None])[0]
            if not filehash:
                raise RuntimeError("CPU wheel index omitted hash")
            with request(urllib.parse.urlunparse(parsed._replace(fragment=""))) as response:
                size = int(response.headers["Content-Length"])
            return {"name": name, "version": version, "filename": filename,
                    "url": urllib.parse.urlunparse(parsed._replace(fragment="")), "sha256": filehash,
                    "size_bytes": size, "index": "https://download.pytorch.org/whl/cpu/torch/"}
        raise RuntimeError("Pinned CPU-only CPython313 Windows torch wheel unavailable")
    metadata = get_json(f"https://pypi.org/pypi/{name}/{version}/json")
    for entry in metadata["urls"]:
        if entry["packagetype"] != "bdist_wheel" or entry.get("yanked"):
            continue
        _, wheel_version, _, wheel_tags = parse_wheel_filename(entry["filename"])
        compatible = set(tags).intersection(wheel_tags)
        if compatible and wheel_version == Version(version):
            choices.append((min(tags[tag] for tag in compatible), entry))
    if not choices:
        raise RuntimeError(f"No reviewed binary-compatible wheel: {name}=={version}")
    entry = min(choices, key=lambda item: (item[0], item[1]["filename"]))[1]
    return {"name": name, "version": version, "filename": entry["filename"], "url": entry["url"],
            "sha256": entry["digests"]["sha256"], "size_bytes": entry["size"],
            "index": f"https://pypi.org/pypi/{name}/{version}/json"}


def read_lock():
    """The release lock is an input, never regenerated during acquisition."""
    result = {}
    for raw in (ROOT / "staging" / "requirements-cpu-win-cp313.lock").read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith("#"):
            continue
        found = re.fullmatch(r"([a-z0-9-]+)==([^ ]+) --hash=sha256:([a-f0-9]{64})", raw)
        if not found or found[1] in result:
            raise RuntimeError("Malformed or duplicate committed wheel lock")
        result[found[1]] = (found[2], found[3])
    if {name: version for name, (version, _) in result.items()} != PINS:
        raise RuntimeError("Committed lock does not match the declared dependency closure")
    return result


def wheels():
    if sys.version_info[:2] != (3, 13) or sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("This lock requires Windows CPython 3.13 x64")
    locked = read_lock()
    artifacts = []
    environment = default_environment()
    environment["extra"] = ""
    normalized = {canonicalize_name(name): version for name, version in PINS.items()}
    for name, version in PINS.items():
        item = resolve_wheel(name, version)
        if locked.get(name) != (version, item["sha256"]):
            raise RuntimeError(f"Public wheel differs from committed lock: {name}")
        target = ARTIFACTS / "wheels" / item["filename"]
        print("STAGE_WHEEL", name, version, item["size_bytes"], flush=True)
        download(item["url"], target, item["sha256"], item["size_bytes"])
        with zipfile.ZipFile(target) as archive:
            infos = archive.infolist()
            pth = {info.filename: hashlib.sha256(archive.read(info.filename)).hexdigest()
                   for info in infos if info.filename.endswith(".pth")}
            reviewed_pth = {"distutils-precedence.pth": "2638ce9e2500e572a5e0de7faed6661eb569d1b696fcba07b0dd223da5f5d224"}
            if pth and (name != "setuptools" or pth != reviewed_pth):
                raise RuntimeError(f"Unreviewed .pth startup entry in {name}")
            item["pth_files"] = pth
            item["pth_execution"] = "disabled: sys.path bootstrap, never site.addsitedir"
            if any(Path(info.filename).is_absolute() or ".." in Path(info.filename).parts for info in infos):
                raise RuntimeError("Unsafe wheel member path")
            metadata_files = [info.filename for info in infos
                              if info.filename.endswith(".dist-info/METADATA") and len(Path(info.filename).parts) == 2]
            if len(metadata_files) != 1:
                raise RuntimeError("Ambiguous wheel metadata")
            message = email.message_from_bytes(archive.read(metadata_files[0]))
            item["uncompressed_bytes"] = sum(info.file_size for info in infos)
            item["requires_dist"] = message.get_all("Requires-Dist", [])
            item["license_files"] = [info.filename for info in infos if "license" in info.filename.lower() or "notice" in info.filename.lower()]
            item["native_members"] = [info.filename for info in infos if info.filename.endswith((".dll", ".pyd"))]
            for raw in item["requires_dist"]:
                requirement = Requirement(raw)
                if requirement.marker and not requirement.marker.evaluate(environment):
                    continue
                dep = canonicalize_name(requirement.name)
                if dep not in normalized or Version(normalized[dep]) not in requirement.specifier:
                    raise RuntimeError(f"Unpinned/incompatible required dependency: {name}: {raw}")
        artifacts.append(item)
        write(RECEIPTS / "cpu_wheels.json", {"status": "STAGING", "wheels": artifacts})
    projected = artifact_bytes() + sum(item["uncompressed_bytes"] for item in artifacts) + 300_000_000
    if projected > MAX_BYTES:
        raise RuntimeError(f"Projected installation plus models exceeds 3 GiB: {projected}")
    write(RECEIPTS / "cpu_wheels.json", {"status": "STAGED_LOCK_VERIFIED",
          "created_at": datetime.now(timezone.utc).isoformat(), "wheels": artifacts,
          "download_bytes": sum(item["size_bytes"] for item in artifacts),
          "uncompressed_bytes": sum(item["uncompressed_bytes"] for item in artifacts),
          "projected_total_with_model_reserve": projected})
    print("WHEELS_STAGED", projected, flush=True)


def install():
    receipt = json.loads((RECEIPTS / "cpu_wheels.json").read_text())
    if receipt["status"] != "STAGED_LOCK_VERIFIED":
        raise RuntimeError("Wheel staging receipt not complete")
    site = ARTIFACTS / "site"
    if site.exists() and any(site.iterdir()):
        raise RuntimeError("Refusing to overwrite existing target environment")
    command = [sys.executable, "-I", "-m", "pip", "--isolated", "--disable-pip-version-check",
               "install", "--no-index", "--no-cache-dir", "--no-deps", "--require-hashes",
               "--only-binary=:all:", "--no-compile", "--find-links", str(ARTIFACTS / "wheels"),
               "--target", str(site), "-r", str(ROOT / "staging" / "requirements-cpu-win-cp313.lock")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    write(RECEIPTS / "cpu_install.json", {"returncode": result.returncode,
          "stdout": result.stdout.replace(str(ROOT), "<WORKBENCH>"),
          "stderr": result.stderr.replace(str(ROOT), "<WORKBENCH>"),
          "artifact_bytes": artifact_bytes(), "target": "<ARTIFACTS>/site"})
    if result.returncode or artifact_bytes() > MAX_BYTES:
        raise RuntimeError("CPU wheel installation failed or exceeds staging bound")
    print("CPU_RUNTIME_INSTALLED", artifact_bytes(), flush=True)


def models():
    manifests = []
    for key, (model_id, revision) in MODELS.items():
        metadata = get_json(f"https://huggingface.co/api/models/{model_id}/revision/{revision}?blobs=true")
        if metadata["sha"] != revision:
            raise RuntimeError("Immutable HF revision mismatch")
        selected = [item for item in metadata["siblings"] if item["rfilename"] in ALLOW_FILES]
        names = {item["rfilename"] for item in selected}
        if not {"model.safetensors", "config.json", "tokenizer.json", "README.md"}.issubset(names):
            raise RuntimeError("Required pinned model files are absent")
        manifest = {"model_id": model_id, "revision": revision, "files": [],
                    "source": f"https://huggingface.co/{model_id}/tree/{revision}",
                    "model_code": "standard_transformers_no_remote_code", "weights": "safetensors_fp32"}
        for item in selected:
            name = item["rfilename"]
            target = ARTIFACTS / "models" / key / name
            url = f"https://huggingface.co/{model_id}/resolve/{revision}/{name}"
            expected = item.get("lfs", {}).get("sha256")
            print("STAGE_MODEL", key, name, item.get("size"), flush=True)
            actual = download(url, target, expected, item.get("size"))
            data = target.read_bytes() if expected is None else None
            if data is not None:
                git_blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                if git_blob != item["blobId"]:
                    raise RuntimeError("Pinned HF git blob identity mismatch")
            manifest["files"].append({"path": name, "sha256": actual, "size_bytes": target.stat().st_size,
                                      "git_blob_id": item["blobId"], "lfs_sha256": expected})
        write(ARTIFACTS / "models" / key / "manifest.json", manifest)
        manifests.append(manifest)
        write(RECEIPTS / "cpu_models.json", {"status": "STAGING", "models": manifests})
    write(RECEIPTS / "cpu_models.json", {"status": "STAGED_NOT_YET_EXECUTED", "models": manifests,
          "created_at": datetime.now(timezone.utc).isoformat(), "artifact_bytes": artifact_bytes(),
          "size_limit_bytes": MAX_BYTES})
    print("MODELS_STAGED", artifact_bytes(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("wheels", "install", "models"))
    parser.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    args = parser.parse_args()
    ARTIFACTS = args.artifacts.expanduser().resolve()
    RECEIPTS = ARTIFACTS / "receipts"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    try:
        {"wheels": wheels, "install": install, "models": models}[args.action]()
    except Exception as exc:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        write(RECEIPTS / f"failure-{stamp}.json", {"action": args.action, "status": "STAGING_FAILED",
              "error_type": type(exc).__name__, "error": str(exc), "artifact_bytes": artifact_bytes()})
        raise
