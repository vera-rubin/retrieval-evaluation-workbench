# Results and validation records

These runs used the standalone evaluator with the fixed 240-token / 32-overlap /
equal-weight / RRF-60 protocol. The original held-out queries were already known;
the configuration and labels were reused without tuning.
Every five-method run used k=10, seed 17, one CPU inference process and at
most two compute threads. The report uses the first held-out pass as primary.

| Execution | Raw observations | Inspectable report |
|---|---|---|
| Development, 94 queries x 5 methods | [run.json.gz](release-development/run.json.gz) | [HTML](release-development/report.html) / [Markdown](release-development/report.md) |
| Primary held-out, 94 queries x 5 methods | [run.json.gz](release-heldout/run.json.gz) | [HTML](release-heldout/report.html) / [Markdown](release-heldout/report.md) |
| Held-out repeat, 94 queries x 5 methods | [run.json.gz](release-heldout-repeat/run.json.gz) | [HTML](release-heldout-repeat/report.html) / [Markdown](release-heldout-repeat/report.md) |

All methods were `EXECUTED`, all observations validated, and no resource failure
was reported. Each method's quality means use 79 answerable queries; its fifteen
empty-relevance requests are separate diagnostics. The three runs contain
1,410 method/query searches over the same dataset and known query splits.

The [normal repeat comparison](repeat-comparison.json) is compatible with zero
quality deltas and no regression. Its [HTML](repeat-comparison/report.html) and
[Markdown](repeat-comparison/report.md) show changes, including the observed timing
variation. [summary.json](summary.json) is rescored from the three raw bundles
and includes source identities, raw SHA-256 values, categories, diagnostics,
and query detail. Regenerate it from the root with:

```powershell
.\.venv\Scripts\python.exe -I scripts\summarize_results.py results\release-development\run.json.gz results\release-heldout\run.json.gz results\release-heldout-repeat\run.json.gz --out .artifacts\recomputed-summary.json
```

The measured evaluator commit is
`72e9ed05d363d2806c5b7afb9baac120a30af8bb`, with source-file digest
`467ed8078f588aca1104e2440b6aa05bb52c51189ad08350d106bb4d9629ab13` and dataset
digest `615b98beee8789b849ed0255f389f5308956af34e67b96fa1d8764888a61510b`.
Later packaging, report and test changes have their own identities. Source-file
hashes identify the evaluator used by these runs.
The 29-wheel lock and method identities record exact dependencies and model
artifacts. The dataset metadata differs from the earlier experiment, so ordinary
comparison rejects that pair on `identity.fixture_digest`.

## Software tests and archive checks

Each linked test record identifies the files and execution it checked.

| Event | Recorded result | Execution scope |
|---|---|---|
| [Initial clean archive](validation/clean-archive.json) | 164 tests passed, including 34 reliability and 16 standalone tests; dataset and trace checks passed | Dependencies and both pinned models acquired afresh; 94 lexical queries executed; no semantic inference from this archive |
| [Expanded test suite](validation/evaluator-171.json) | 171 tests from seven files; zero skips, failures or errors | Checkout test run after adding tests |
| [171-test rerun](validation/evaluator-171-candidate.json) | All 171 executed successfully | Text files matched to the declared LF archive format; evaluator source and raw results unchanged |
| [Pre-commit checkout](validation/editorial-171.json) | 171 tests plus the repeated 34-test reliability subset; dataset and trace checks passed | Presentation edits were present before commit; recorded HEAD and evaluator/test hashes identify that state |
| [93-file archive at 5e71d766](validation/archive-5e71d766.json) | 171 tests with zero skips/failures/errors; exact files verified; dataset and trace checks passed; report rebuild byte-identical | Existing dependencies reused; no new acquisition or separate retrieval run |

The 34 reliability tests are a subset of the full suite. The five-method
retrieval runs at the top of this page are separate executions from the clean
archive's lexical-only run. The archive summary retains its commit, tree,
archive digest and source test-record digest.

The assembled dataset also has individual [validation](validation/fixtures.json),
[correct-trace](validation/correct-traces.json) and
[incorrect-trace](validation/incorrect-traces.json) results. Twelve correct cases
were accepted and their twelve deliberately incorrect variants were rejected.
These are paired observations of the same twelve cases.

The [missing-dependency test](validation/missing-dependency.json) exited one,
reported `NOT_RUN` / `APSW_NOT_STAGED`, and produced zero query observations.

## Checks on retained results

The [arithmetic check](validation/arithmetic-source-review.json), executed on
10 September 2026 UTC, recomputed values from all three runs using a separate
standard-library implementation: 13 self-checks, 7,140 numerical comparisons,
maximum absolute difference 3.3306690738754696e-16 within 1e-12. It reuses the
recorded ranks and does not execute retrieval.

The [tokenizer inspection](validation/tokenizer-source-review.json) used the
pinned tokenizer files and existing chunker. Each model produced 588 chunks
from 291 indexed records: 576 one-chunk fields and six two-chunk bodies, with
exact coverage and no split titles. No model weights or forward passes were used.
See [verification commands and scope](../docs/VERIFICATION.md) for both checks.

Some test records are declared summaries with machine-specific paths replaced
by location tokens. Their recorded source identities and outcomes are preserved.
The raw retrieval bundles retain their original bytes; report and score
generation reads them without modification.
