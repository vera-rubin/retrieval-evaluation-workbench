# Evidence checks and reproduction targets

These checks support the accompanying report without changing its inputs,
rankings or numerical tables. The original held-out query split is already
known. No new embedding execution or configuration selection was performed for
the source-informed clarifications.

## Retained-rank arithmetic

`scripts/summarize_results.py` calls `hippo_eval.metrics.score_bundle`; the report
builder uses that summarizer. They regenerate tables and validate the result
contract, but are not separate arithmetic implementations.

The earlier 1e-12 agreement statement referred to a separately written
calculation of the development and primary held-out aggregates. That checker
used the evaluator for its reference scores and comparison, but calculated its
second set of recall, precision, MRR and nDCG values in its own loops. It did not
independently recalculate the repeat, and its receipt did not bind the checker
hash or explicitly record the tolerance. That historical event has not been
rerun or retroactively given a stronger identity.

The new [check_arithmetic.py](../scripts/check_arithmetic.py) uses only the Python
standard library and does not import the evaluator. It recalculates metrics
from raw ranked IDs and fixture relevance, then compares them with the retained
summary after checking raw-file, fixture and configuration identities. It
supports successful completed runs and refuses missing or failed observations;
it is not a second full result-contract validator or a relevance-label audit.

The [dated receipt](../results/validation/arithmetic-source-review.json) records
the new execution on 10 September 2026 UTC: three raw runs, five methods per
run, 13 literal/rejection self-checks, and 7,140 numerical comparisons across
per-query, method and category values. Maximum absolute difference was
3.3306690738754696e-16, within 1e-12. The self-checks use small hand-calculated
examples and malformed inputs; they are not additional benchmark queries.
The formulas were separately implemented within the same model-assisted
project, not independently certified by another institution.

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
That field name does not imply that an answerability decision rule was tested.
An error is not counted as a successful empty-list response.

## Actual chunk coverage

The [tokenizer-only utility](../scripts/inspect_chunk_coverage.py) checks the
staged tokenizer files against the pinned model revisions and retained run
hashes, then calls the existing chunker with the established 240-token budget
and 32-token overlap. It disables model frameworks and tokenizer parallelism,
uses local files only, and loads no model weights or forward passes.

The [separate inspection receipt](../results/validation/tokenizer-source-review.json)
identifies the utility, inputs, tokenizers and execution. For each model the
291 indexed records have 582 nonempty title/body fields, yielding 588 chunks:
576 one-chunk fields and six two-chunk bodies; no title splits and no field
has more than two chunks. Exact source substrings cover all nonempty fields.
This is observed token coverage, not an inference from character lengths or
the aggregate count 588. The corpus gives limited evidence about long-document
chunking. Focused software tests use `SimpleOffsetTokenizer`, including an
artificial six-token budget; those tests do not execute either embedding model.

```powershell
.\.venv\Scripts\python.exe -I -S -B scripts\inspect_chunk_coverage.py --artifacts .artifacts --out .artifacts\checks\tokenizers-new.json
```

The utility is bounded to the retained corpus/configuration and already staged
assets. It is not a download tool or a new retrieval benchmark. Model weights
and dependency files remain outside the source archive.

## Archive and checkout evidence

| Event | What executed | What was not established |
|---|---|---|
| [Initial clean archive: 164 tests](../results/validation/clean-archive.json) | Fresh documented acquisition, tests, fixture/trace checks, and 94 lexical queries | No semantic inference from that archive; no cross-host result equality |
| [Pre-commit editorial checkout: 171 tests](../results/validation/editorial-171.json) | Unchanged evaluator/test file identities, fixtures, trace pairs and focused reliability checks | Its observed HEAD does not identify the later edited commit; no new model benchmark |
| [Exact 93-file archive at 5e71d766](../results/validation/archive-5e71d766.json) | 171 tests with zero skips/failures/errors, fixtures, twelve trace pairs, exact file checks and byte-identical report rebuild | Reused runtime dependencies; no new acquisition or separate retrieval run |

The 34-test reliability group is a subset of the 171-test suite, not an additional
34 distinct tests. The archive summary is a disclosed derivative with its
original receipt hash and archived commit; private approval records remain
private. Each later final candidate repeats archive checks with a new exact
commit/tree and receipt in its approval package. Historical checks never become
observations of changed release bytes.

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
not provide all component ranks used by that fusion. The report retains the
observed miss without inventing a component-rank explanation.

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
raises an error on excess. The supervisor polls the owned worker every 100 ms
and kills it on observed RSS/time excess. Both are sampled abort checks, not an
OS allocation ceiling or a guarantee that a transient peak was observed.

Rescoring retained bundles, checking their arithmetic and rendering the report
reuse the existing ranks. Re-executing retrieval on another host is a different
target requiring new observations; neither same-host repeats nor archive tests
establish identical cross-host scores, timing or resource use.
