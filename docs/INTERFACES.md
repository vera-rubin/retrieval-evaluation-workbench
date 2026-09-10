# Interfaces and result contracts

This guide describes the adapter methods, dataset formats, result bundles and
failure states used by the evaluator.

## Retrieval adapter

`hippo_eval.contracts.RetrievalAdapter` defines the adapter:

```python
class RetrievalAdapter:
    name: str
    identity: dict
    def build(self, records: list[dict], config: dict) -> dict: ...
    def search(self, query: dict, eligible_ids: set[str], k: int) -> list[dict]: ...
    def fetch(self, record_id: str) -> dict: ...
    def close(self) -> None: ...
```

`build` receives complete synthetic records and a validated configuration. It
returns measured load/index time, record/chunk counts and available resource
observations. `identity` describes the backend, exact model revision, tokenizer,
pooling, query prefix, normalization and actually loaded dependency versions.
An unavailable adapter reports `NOT_RUN`; an attempted failed operation reports
`FAILED` or a query error. A method that did not execute has no score.

`search` receives a precomputed eligible-ID set. It must return unique
record IDs with finite scores, at most `k` entries, and sufficient chunk
provenance for returned semantic hits. This boundary separates ranking from
project, owner, task, status, revision and evidence filters. Caller authentication
is outside this interface.

`fetch` returns an independent full record, including exact retained body and
provenance. The evaluator compares returned bytes and metadata with the dataset.
Semantic chunks retain field names, character offsets, token counts and content
hashes. Record-level deduplication follows similarity
ranking, and full records are not silently truncated to fit a model.

Another implementation can translate its responses at this boundary and supply
its own identity. The bundled semantic implementation uses CPU PyTorch embeddings
with NumPy cosine scanning.

### Bounds of the bundled implementations

The bundled lexical search rejects more than 10,000 retained-body eligible
rowids when constructing its parameterized SQL query. This is a bound on that
SQL search path, not on corpus storage, the semantic scan, or all possible
adapters. Its query expression accepts at most 256 distinct terms after literal
Unicode extraction and deduplication; a larger set raises `RetrievalInputError`
instead of silently truncating it. A query with no extracted terms returns no
lexical matches. Both restrictions also affect a hybrid's lexical component.

The semantic path instead checks model token limits (512 for BGE, 256 for
MiniLM), including query prefixes and special tokens, and explicitly rejects
overlong inputs. Null bodies exclude the entire record at build time. A
non-null field consisting only of whitespace produces no chunk. A successful
semantic search with positive k returns a candidate if an eligible indexed
passage exists; unsuccessful loading/encoding and empty indexed pools do not
meet that condition.

The hybrids request `len(eligible_ids)` results from each component before
fusion, then choose the final top-k records. Semantic search supplies all
eligible records with indexed passages; lexical search supplies only matches
to the extracted query terms. A lexical nonmatch receives no lexical RRF
contribution. Lexical ties use rowids assigned in sorted record-ID order;
semantic and hybrid ties also use record ID. These are properties of the
bundled implementations, not universal requirements on every future adapter.

## Dataset, run and identity records

The corpus and query schemas are defined in `hippo_eval/contracts.py` and
validated by `hippo_eval/fixtures.py`. Query rules identify applicability and
explicit relevance grades. Titles and bodies are searchable; query IDs,
relevance maps and rationales are not inserted into indexed text.

A `hippo-eval-run/v2` bundle records its split, source-file hashes, dataset and
dependency digests, configuration identity, method identities, individual
rankings, timings, fidelity observations, execution states and integrity errors.
The Git commit belongs to the standalone checkout when present. A downloaded
source archive records `git_head: null` and `source_origin: source_archive`,
while preserving the actual source-file hashes used for validation.

Portable runtime records use `<ARTIFACTS>/site` for the selected dependency site.
Executable content is identified by hash and executable name.

`hippo-eval-reproduction/v1` explicitly declares a known-split reproduction of
the previously selected fixed protocol. It sets `selection_performed: false`
and `original_heldout_already_known: true`. It binds current source, dependencies,
dataset, configuration and pinned model specifications. A change invalidates
the declaration. The development-only selection interface is available for
separate experiments with new datasets and an appropriate split protocol.

`score` recalculates analysis from supplied observations and rejects malformed,
truncated, inconsistent or mixed-configuration records. `compare` recalculates
both sides before comparing compatible scored results. Source changes are
explicitly reported; dataset, dependency, metric, split, configuration and
method-identity requirements remain enforced.

## Scenario observations

`scenarios/cases.json` specifies literal expected observations. `correct.json`
and `incorrect.json` contain paired example traces for testing the checker.
The trace format requires authorship metadata and a review note.
The checker validates case and step coverage/order, exact JSON types, keys,
values and complete observations against the expected values.

An external adapter can supply the same trace schema from an actual system,
with a documented execution context. The bundled traces test checker behavior;
they do not execute authentication, persistence, process replacement or recovery.

## Test records and failure states

The test command emits `hippo-eval-test-receipt/v2`. `PASSED` requires discovered
files, discovered cases, at least one executed test, no failures/errors and
unchanged source/test identities. `DISCOVERY_FAILED`, `ZERO_TESTS_EXECUTED`,
`TEST_FAILURES` and `SOURCE_CHANGED` identify different failure states.

Comparison outputs are retained even when the command exits unsuccessfully.
Inference-lock tests cover live owners, abandoned owners, PID reuse, zombie
ownership, ambiguous state and deterministic finally cleanup.
