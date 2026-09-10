# Release-validation evidence

These are new executions of the standalone export. They are not relabeled
historical bundles. The original held-out queries are already known; the fixed
240-token / 32-overlap / equal-weight / RRF-60 protocol was reused without tuning.
Every five-method run used k=10, seed 17, one owned CPU inference process and at
most two compute threads. The report uses the first held-out pass as primary.

| Execution | Raw observations | Inspectable report |
|---|---|---|
| Development, 94 queries x 5 methods | [run.json.gz](release-development/run.json.gz) | [HTML](release-development/report.html) / [Markdown](release-development/report.md) |
| Primary held-out, 94 queries x 5 methods | [run.json.gz](release-heldout/run.json.gz) | [HTML](release-heldout/report.html) / [Markdown](release-heldout/report.md) |
| Held-out repeat, 94 queries x 5 methods | [run.json.gz](release-heldout-repeat/run.json.gz) | [HTML](release-heldout-repeat/report.html) / [Markdown](release-heldout-repeat/report.md) |

All methods were EXECUTED, all observations validated, and no resource failure
was reported. Each method's quality means use 79 answerable queries; its fifteen
empty-gold requests are separate diagnostics. There are 1,410 method/query
searches across the three runs. This is not 1,410 independent experimental units.

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
`467ed8078f588aca1104e2440b6aa05bb52c51189ad08350d106bb4d9629ab13` and fixture
digest `615b98beee8789b849ed0255f389f5308956af34e67b96fa1d8764888a61510b`.
Later packaging, report and test additions are not claimed as that run's Git
head. Source-file hashes bind the unchanged evaluator to the final candidate.
The 29-wheel lock and method identities record exact dependencies and model
artifacts. The public fixture envelope differs from the earlier experiment;
ordinary comparison correctly rejects that cross-envelope pair.

## Validation receipts

The [93-file source archive at 5e71d766](validation/archive-5e71d766.json) has a
separate, publication-safe summary of its exact validation: 171 tests, zero
skips/failures/errors, fixture validation, twelve correct and twelve incorrect
trace variants, and byte-identical report rebuilding. It reused local runtime
dependencies and did not acquire assets or execute a separate retrieval run.
The summary preserves that archived commit and original private receipt digest;
it does not claim that later corrections were tested by the same event.

The previous editorial checkout [executed all 171 evaluator tests](validation/editorial-171.json)
from seven test files, with zero skips, failures, or errors. The focused 34-test
reliability group also passed; fixture validation passed, and the twelve correct
scenario variants were accepted while their twelve incorrect counterparts were
rejected. This receipt preserves its observed pre-commit HEAD and binds the
unchanged evaluator/test files explicitly. It does not claim new model runs.
Each final downloadable archive is checked separately and bound to its own
commit, tree, and archive digest in the accompanying approval package.

The receipts below remain historical observations with their original identities.

[Clean-archive validation](validation/clean-archive.json) records 164 applicable
tests in the initial standalone source checkpoint, including 34 reliability and
16 standalone tests. It also records fixture validation, 12 correct traces
accepted, 12 deliberate incorrect traces rejected, and 94 lexical queries run
from an archive without Git history. Dependencies and both pinned models were
acquired afresh through the documented public path. No full semantic run is
claimed from that archive; the five-method runs above used the standalone Git
checkout with its own freshly acquired environment.

The [missing-dependency probe](validation/missing-dependency.json) exited one,
reported NOT_RUN / APSW_NOT_STAGED and zero query observations. It is an actual
negative execution, not a fabricated retrieval score. Final test additions and
the assembled archive are checked separately. The expanded suite
[executed 171 tests](validation/evaluator-171.json), with zero skips, failures,
or errors. The [candidate rerun](validation/evaluator-171-candidate.json) again
executes 171 after matching text files to the declared LF archive format;
bound evaluator source and raw benchmark bundles did not change.
[Fixtures](validation/fixtures.json) and the
[correct](validation/correct-traces.json) / [incorrect](validation/incorrect-traces.json)
trace checks were also rerun on the assembled publication tree. These are new
receipts, not replacements for earlier validation.

Receipts in this directory are disclosure-reviewed derivatives of new local
validation logs: location tokens replace personal paths. They are explicitly
named as sanitized summaries; raw benchmark bundles retain their original bytes.
Report and score regeneration never changes a retained run.
