# Evidence checks and reproduction targets

This guide distinguishes checks on retained rankings, tokenizer inspection,
software tests and retrieval executions. The held-out query split is already
known. Arithmetic and report rebuilding reuse its recorded rankings.

## Retained-rank arithmetic

`scripts/summarize_results.py` calls `hippo_eval.metrics.score_bundle`; the report
builder uses that summarizer. They regenerate tables and validate the result
contract, but are not separate arithmetic implementations.

An earlier arithmetic check covered development and primary held-out aggregates.
It used the evaluator for reference scores, then calculated recall, precision,
MRR and nDCG separately. It excluded the repeat, and its test record omitted the
checker hash and explicit tolerance. The dated check below is a separate event.

The [check_arithmetic.py](../scripts/check_arithmetic.py) utility uses only the Python
standard library and does not import the evaluator. It recalculates metrics
from raw ranked IDs and dataset relevance labels, then compares them with the
retained summary after checking raw-file, dataset and configuration identities. It
supports successful completed runs and refuses missing or failed observations.
Its scope is arithmetic; result-contract and label checks are separate.

The [test record](../results/validation/arithmetic-source-review.json) records
execution on 10 September 2026 UTC: three raw runs, five methods per
run, 13 literal/rejection self-checks, and 7,140 numerical comparisons across
per-query, method and category values. Maximum absolute difference was
3.3306690738754696e-16, within 1e-12. Its 13 self-checks use hand-calculated
examples and malformed inputs, separate from the benchmark queries. The formulas
are a second implementation within this project.

```powershell
.\.venv\Scripts\python.exe -I -B scripts\check_arithmetic.py --out .artifacts\checks\arithmetic-new.json
```

Under precision's fixed k=10 denominator, held-out labels allow at most
158/(79*10)=0.2000 and development labels 170/(79*10)=0.2151898734. Each split's
largest relevance set has five records, so all gold records can fit within k;
the general ceiling uses min(k, gold-count) per query. Grades 1-3 count as
relevant. The primary held-out relevant record-query hit counts are lexical
144, BGE 153, MiniLM 154, and both hybrids 152. Macro recall averages each
query's hits/gold-count; it is not total hits divided by all labels. A net hit
difference alone cannot identify how many rankings or query outcomes differ.

Empty-gold queries are excluded from the four primary quality means. Separate
diagnostics count successful empty lists, queries with nonempty lists, total
returned records, and an empty-list rate named `unanswerable_abstention_rate`.
This rate describes returned lists, not an answerability decision. An error
does not count as a successful empty-list response.

## Tokenizer and chunk coverage

The [tokenizer-only utility](../scripts/inspect_chunk_coverage.py) checks the
staged tokenizer files against the pinned model revisions and retained run
hashes, then calls the existing chunker with the established 240-token budget
and 32-token overlap. It disables model frameworks and tokenizer parallelism,
uses local files only, and loads no model weights or forward passes.

The [inspection record](../results/validation/tokenizer-source-review.json)
identifies the utility, inputs, tokenizers and execution. For each model the
291 indexed records have 582 nonempty title/body fields, yielding 588 chunks:
576 one-chunk fields and six two-chunk bodies; no title splits and no field
has more than two chunks. Exact source substrings cover all nonempty fields.
These counts come from the tokenizer inspection. The corpus exercises at most
two chunks per field, which limits its coverage of long-document behavior.
Software tests also use `SimpleOffsetTokenizer`, including a six-token budget;
those tests do not execute either embedding model.

```powershell
.\.venv\Scripts\python.exe -I -S -B scripts\inspect_chunk_coverage.py --artifacts .artifacts --out .artifacts\checks\tokenizers-new.json
```

The utility uses the retained dataset/configuration and already staged assets.
Acquire dependencies and tokenizer files before running it; it downloads nothing.

## Archive and checkout evidence

| Event | Checks performed | Execution scope |
|---|---|---|
| [Initial clean archive: 164 tests](../results/validation/clean-archive.json) | Fresh documented acquisition, tests, dataset/trace checks, and 94 lexical queries | Both models acquired; semantic inference not run from this archive |
| [Expanded suite: 171 tests](../results/validation/evaluator-171.json) | Seven test files; zero skips, failures or errors | Checkout validation of the expanded test suite |
| [171-test rerun](../results/validation/evaluator-171-candidate.json) | Test rerun after text files were matched to the declared LF archive format | Evaluator source and raw results unchanged |
| [Pre-commit checkout: 171 tests](../results/validation/editorial-171.json) | Evaluator/test hashes, dataset, trace pairs and focused reliability checks | Edits were present; recorded HEAD identifies the pre-commit state |
| [93-file archive at 5e71d766](../results/validation/archive-5e71d766.json) | 171 tests with zero skips/failures/errors, dataset, twelve trace pairs, exact file checks and byte-identical report rebuild | Existing dependencies reused; no acquisition or separate retrieval run |

The 34-test reliability group is a subset of the 171-test suite. The archive
summary records its archived commit and the hash of its source test record.
Each event applies to those recorded files. The [results ledger](../results/README.md)
links the separate test and retrieval outputs.

## Retrieval behavior and execution limits

All 188 eligible-pool statistics use `contracts.eligible`, which rejects null
bodies before applying the remaining rules. In this corpus every eligible
record has indexed passages. A successful semantic search with positive k
returns the best passage of each eligible record, up to k, without a similarity
threshold. Fusion inherits those candidates when both component searches
succeed. Missing models, encoding errors and zero indexed eligible passages
do not meet these conditions.

The lexical component contributes term matches only. Each hybrid requests full
available component rankings before final top-k fusion. A lexical nonmatch gets
no lexical reciprocal-rank contribution. This source-level mechanism does not
by itself identify the cause of the Orchard miss: retained top-ten lists do
not provide all component ranks used by that fusion.

The [interface guide](INTERFACES.md#bounds-of-the-bundled-implementations) scopes
the 10,000-row SQL bound and 256 deduplicated lexical-term cap to the affected
lexical/hybrid paths. Semantic query limits are instead model-token limits.
Lexical rowids follow sorted record IDs, so its rowid tie-break agrees with
the report's stable-ID rule.

`torch.manual_seed(17)` is called at model load. Eval mode, inference mode and
stable ranking do not prove seed irrelevance or deterministic execution across
hosts. The semantic load timer includes artifact checks and deferred framework
imports; later methods reuse imported modules. Hybrid load/index observations
sum actual component builds. Query timing includes eligibility, search, full
fetch and fidelity checks, while setup/indexing is outside that timer. The
different recorded build and query times have no isolated causal explanation.

The semantic engine checks its own RSS after load and every encoding batch and
raises an error on excess. The supervisor polls the run's inference process every 100 ms
and kills it on observed RSS/time excess. Both are sampled abort checks, not an
OS allocation ceiling or a guarantee that a transient peak was observed.

To measure retrieval on another host, execute the methods and save new runs.
Same-host repetition and archive tests do not establish cross-host equality of
scores, timing or resource use.
