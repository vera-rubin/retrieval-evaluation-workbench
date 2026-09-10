# Reproducible Retrieval Evaluation

**A Workbench for Lexical, Semantic, and Hybrid Search**

Nathan Chandrasekar · [ORCID](https://orcid.org/0009-0003-9702-8164)
Proposed software v1.0.0 · release candidate for review

I built this workbench to compare lexical search, two compact local embedding
models, and their hybrid combinations under one inspectable evaluation contract.
I ask how ranking quality, recall, and query latency differ when methods share
the same synthetic project records, eligibility rules, and complete-record checks.

The corpus has 300 records; the nine deleted records have null bodies, leaving
291 records whose titles and bodies are indexed. Both query splits use that same
corpus, and **each query ranks only its eligible records**: pools range from 1
to 43 records, with median 36, after excluding null bodies and applying the
query's rules. The 188 labeled queries
cover facts, decisions, preferences, observations, code references, historical
revisions, and requests requiring several records.

The workbench runs SQLite FTS5 BM25, BGE-small-en-v1.5, all-MiniLM-L6-v2, and two
equal-weight reciprocal-rank-fusion combinations. It validates fixtures and
observations, distinguishes missing execution from retrieval errors, compares
compatible runs, and produces JSON, Markdown, and static HTML reports. Twelve
scenario cases each have a correct and a deliberately incorrect trace variant.
The contribution is the evaluation software and documented comparison.

## Principal findings

On the 79 answerable queries in the original held-out split, BGE has the highest
nDCG@10 (0.9588) and MRR@10 (0.9852). MiniLM has slightly higher recall@10
(0.9863 versus 0.9831); lexical recall is 0.9363. The two equal-weight hybrids
do not consistently improve over their semantic components. A held-out repeat
preserves every quality aggregate. The existing 54-query larger-pool subset is
reported beside the full analysis, without replacing it. On the other 25
answerable held-out queries, semantic/hybrid recall saturates because top ten
covers every eligible indexed record; lexical recall and all methods' ideal
nDCG on those cases are observed results.

Warm p50 latency is reported for the primary and repeat passes together:
BGE 20.74 / 11.69 ms, MiniLM 11.95 / 5.83 ms, and lexical 2.74 / 1.60 ms,
each over 94 requests per pass. These timings include eligibility, search,
full-record fetch, and fidelity hashing. The variation is part of the result;
its cause was not isolated. No monetary or energy savings were measured.

All five methods returned nonempty candidate lists for the fifteen empty-relevance
queries. Successful semantic/fusion searches return candidates when k is positive
and eligible indexed passages exist; this is not an answerability decision rule.
Missing artifacts and failed execution are separate outcomes. Under the declared labels,
counterevidence can count as a false retrieval even when it could help an answerer
reject a false premise.

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

## Report, evidence, and tests

Read the [technical report](report/report.html), its [PDF](report/report.pdf),
or the [editable manuscript](report/manuscript.md). The [results ledger](results/README.md)
links the raw observations, per-query reports, and validation receipts.
The source archive contains **171 evaluator tests**; the ledger distinguishes
current editorial/archive checks from earlier receipts. The twelve correct
trace variants pass and the twelve deliberate incorrect variants are rejected.

See [fixture methodology](fixtures/README.md), [evidence identities](docs/PUBLIC_EVIDENCE.md),
[arithmetic, chunk coverage, and archive verification](docs/VERIFICATION.md),
[interfaces](docs/INTERFACES.md), and the [adapter boundary](docs/ADAPTER_CONTRACT.md).

## Scope and limits

I treat these model-authored fixtures as a controlled software evaluation,
not a human-validated benchmark. Each split has 79 answerable and fifteen
empty-relevance queries. The original held-out split was already known at
re-evaluation; no configuration was retuned. Shared documents, related story
templates, sparse labels, and small eligible pools limit generalization.
Exact retained bytes do not establish relevance or truth, and supplied traces
exercise the checker rather than a deployed service. Validation is limited to
Windows x64; runtime and RSS observations are not service guarantees.

## Citation and license

Use [CITATION.cff](CITATION.cff) for the exact title, name, ORCID, software version,
and research description. No DOI or release date has been assigned. The
accompanying report and software belong to one proposed software release.

Original releasable code, fixtures, documentation, and figures use
[Apache-2.0](LICENSE). Separately acquired dependencies and models retain their
own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).
