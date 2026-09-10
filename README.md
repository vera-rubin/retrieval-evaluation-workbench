# Reproducible Retrieval Evaluation

**A Workbench for Lexical, Semantic, and Hybrid Search**

Nathan Chandrasekar · [ORCID](https://orcid.org/0009-0003-9702-8164)

I built this workbench to compare five search configurations on the same
synthetic dataset and make their results reproducible. It measures which
relevant records are retrieved, how well they are ranked, and how long each
query takes. It also checks that returned records remain complete and that
failed runs are not mistaken for valid measurements.

**Read the [technical report](report/report.html) or [PDF](report/report.pdf).**
Start with the [installation and reproduction guide](docs/INSTALLATION.md),
or inspect the [recorded results](results/README.md).

## Dataset and findings

The dataset contains **300 corpus records, 291 indexed records, and 188 labeled
queries** about fictional projects. Each query searches its eligible records:
pools range from **1 to 43 records, with median 36**. The two query splits share
the corpus and cover facts, decisions, preferences, code references, revisions,
and questions requiring several records.

I compare SQLite FTS5 BM25, BGE-small-en-v1.5, all-MiniLM-L6-v2, and a lexical
hybrid for each embedding model. On the 79 answerable held-out queries:

- **BGE leads ranking quality:** nDCG@10 is 0.9588, versus MiniLM's 0.9379.
  nDCG accounts for relevance grades and a record's position in the ranking.
- **MiniLM has slightly higher recall:** 0.9863, versus BGE's 0.9831 and
  lexical search's 0.9363. Recall is the fraction of labeled relevant records
  retrieved within the first ten results.
- **MiniLM has lower observed query latency than BGE** in both held-out passes.
  The two tested hybrids do not consistently improve on their semantic components.

A repeat preserved every quality aggregate. Small pools make top-ten recall
saturate for the exhaustive semantic and hybrid methods; the report also gives
the [54-query larger-pool analysis](report/report.html#development-repetition-and-larger-pools),
while keeping all 79 answerable queries as the primary comparison.

## Installation and quick reproduction

The tested platform is Windows x64 with CPython 3.13.15. The pinned 29-wheel
dependency set targets CPython 3.13 AMD64. Models run locally on the CPU;
weights and third-party binaries are acquired separately.

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

Run commands sequentially and use a new output directory for each execution.
The defaults permit one inference process, at most two compute threads, and
sampled memory checks at 2 GiB. See [installation](docs/INSTALLATION.md) for
storage requirements, time limits, selected artifact roots, and commands for
rescoring stored rankings without running the models.

## Scope and evidence

This is a small synthetic comparison with related project templates, sparse
labels, and known query splits. The [dataset methodology](fixtures/README.md)
describes construction, filtering, and the limited separate relevance review.
The study evaluates retrieval and record preservation; its supplied scenario
traces test the checker. Other platforms and cross-host result equality have
not been established.

The repository contains 171 evaluator tests, twelve paired scenario cases,
raw results, static per-query reports, and the [editable manuscript](report/manuscript.md).
[Verification records](docs/VERIFICATION.md) distinguish software tests,
arithmetic checks, archive checks, and retrieval executions.
The [interface reference](docs/INTERFACES.md) and [adapter guide](docs/ADAPTER_CONTRACT.md)
explain how to evaluate another retrieval implementation.

## Citation and license

[CITATION.cff](CITATION.cff) provides the author, ORCID, title, software version,
and description. The technical report accompanies software version 1.0.0.

Original code, synthetic data, documentation, and figures use
[Apache-2.0](LICENSE). Acquired dependencies and models retain their own terms;
see [third-party notices](THIRD_PARTY_NOTICES.md).
