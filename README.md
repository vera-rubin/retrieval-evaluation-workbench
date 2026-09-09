# Reproducible Retrieval Evaluation

**A Workbench for Lexical, Semantic, and Hybrid Search**

Nathan John Chandrasekar · [ORCID](https://orcid.org/0009-0003-9702-8164)
Proposed software v1.0.0 · release candidate for review

I compare lexical search, two compact local embedding models, and their hybrid
combinations under one explicit evaluation contract. The research question is
how these methods differ in ranking quality, recall, and measured local cost
when they share a fixed corpus, applicability rules, and exact record checks.

The workbench contains 300 synthetic records and 188 labeled queries. It runs
SQLite FTS5 BM25, BGE-small-en-v1.5, all-MiniLM-L6-v2, and two weighted
reciprocal-rank-fusion combinations. It validates fixtures, checks actual
retrieval observations, distinguishes missing execution from bad retrieval,
compares compatible runs, and produces JSON, Markdown, and static HTML.
Twelve supplied-trace examples exercise observable-result checking.

## Installation and quick reproduction

The supported initial platform is Windows x64 with CPython 3.13.15. The exact
29-wheel lock targets CPython 3.13 AMD64. Other platforms have not been tested.
Use a source checkout or the source archive; this is not a PyPI package.

```powershell
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -I staging\stage_cpu.py wheels
& .\.venv\Scripts\python.exe -I staging\stage_cpu.py install
& .\.venv\Scripts\python.exe -I staging\stage_cpu.py models
& .\.venv\Scripts\python.exe -I workbench.py validate
& .\.venv\Scripts\python.exe -I workbench.py smoke --out .scratch\tests.json
& .\.venv\Scripts\python.exe -I workbench.py prepare-reproduction --out .artifacts\reproduction.json
& .\.venv\Scripts\python.exe -I workbench.py run --reproduction .artifacts\reproduction.json --split development --out results\my-development
& .\.venv\Scripts\python.exe -I workbench.py run --reproduction .artifacts\reproduction.json --split heldout --out results\my-heldout
```

Use a new output directory for every execution. Model acquisition is public and
unauthenticated; inference is local and CPU-only. No model weights or third-party
binaries are bundled. See [installation](docs/INSTALLATION.md) for bounded
resources, selected artifact roots, negative checks, repeats, and acquisition
details. The package retains the established 240-token, 32-overlap, equal-weight,
RRF-60 protocol. `prepare-reproduction` binds this protocol to current inputs;
it does not claim a new blinded experiment or perform configuration selection.

## Interpretation and limits

I treat the synthetic fixtures as a controlled software evaluation, not a
human-validated benchmark or proof of general deployment quality. Each query
split has 79 answerable and 15 unanswerable queries; both use the entire corpus.
The original held-out split is already known. Small, template-related candidate
pools limit discrimination and generalization. Candidate retrieval does not
establish answerability or factual truth, and exact retained bytes do not
establish semantic relevance. Supplied traces do not validate a real service.

See [fixture methodology](fixtures/README.md),
[evidence identities](docs/PUBLIC_EVIDENCE.md),
[interfaces](docs/INTERFACES.md), and the
[adapter boundary](docs/ADAPTER_CONTRACT.md).

## Citation and license

Use [CITATION.cff](CITATION.cff) for the exact title, name, ORCID, software version,
and research description. No DOI or release date has been assigned. The
accompanying report and software belong to one proposed software release.

Original releasable code, fixtures, documentation, and figures use
[Apache-2.0](LICENSE). Separately acquired dependencies and models retain their
own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).
