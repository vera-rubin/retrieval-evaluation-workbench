# Interfaces and result contracts

The public display name is **Reproducible Retrieval Evaluation**. Existing
`hippo_eval` Python imports and `hippo-*` schema identifiers remain unchanged
where possible to preserve compatibility. They are internal format names,
not claims of a released memory product.

## Retrieval adapter

`hippo_eval.contracts.RetrievalAdapter` defines the experimental adapter:

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
`FAILED` or a query error. Neither may manufacture a score.

`search` receives a precomputed synthetic eligible-ID set. It must return unique
record IDs with finite scores, at most `k` entries, and sufficient chunk
provenance for returned semantic hits. This boundary separates ranking from
scope, status, revision and evidence eligibility. It does not authenticate a
caller or establish real access control.

`fetch` returns an independent full canonical record, including exact retained
body and provenance. The evaluator hashes observed bytes and complete metadata
against the fixture, rather than hashing an expected value and calling that an
observation. Semantic chunks retain field names, character offsets, token
counts and content hashes. Record-level deduplication follows similarity
ranking, and full records are not silently truncated to fit a model.

A future system adapter should translate its observed responses at this
boundary. It must not infer production API names, authority or persistence
behavior from these synthetic fixtures. The current semantic implementation
uses CPU PyTorch embeddings with NumPy cosine scanning; it is not a production
vector-database service.

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

## Fixture, run and identity records

The corpus and query schemas are defined in `hippo_eval/contracts.py` and
validated by `hippo_eval/fixtures.py`. Query rules identify applicability and
explicit relevance grades. Titles and bodies are searchable; query IDs,
relevance maps and rationales are not inserted into indexed text.

A `hippo-eval-run/v2` bundle records its split, source-file hashes, fixture and
dependency digests, configuration identity, method identities, individual
rankings, timings, fidelity observations, execution states and integrity errors.
The Git commit belongs to the standalone checkout when present. A downloaded
source archive records `git_head: null` and `source_origin: source_archive`,
while preserving mandatory actual source-file hashes. This does not claim an
unobserved commit or weaken source-digest validation.

New portable runtime receipts use `<ARTIFACTS>/site` rather than a personal
absolute path. Executable content is identified by hash and executable name.
This display transformation does not change canonical record bytes, ranking
scores, fixture labels, model recipes or numerical metrics.

`hippo-eval-reproduction/v1` explicitly declares a known-split reproduction of
the previously selected fixed protocol. It sets `selection_performed: false`
and `original_heldout_already_known: true`. It binds current source, dependencies,
fixtures, configuration and pinned model specifications. A change invalidates
the declaration. The older development-only selection/freeze interface remains
available for separate experiments; it is not used to claim a newly blinded
study of this already known split.

`score` recalculates analysis from supplied observations and rejects malformed,
truncated, inconsistent or mixed-configuration records. `compare` recalculates
both sides before comparing compatible scored results. Source changes are
explicitly reported; fixture, dependency, metric, split, configuration and
method-identity requirements remain enforced. It does not rewrite result
identities to force a comparison.

## Scenario observations

`scenarios/cases.json` specifies literal expected observations. `correct.json`
and `incorrect.json` are separate model-authored example traces, not output
from an implemented memory system. Authorship and a review note are mandatory.
The checker validates case and step coverage/order, exact JSON types, keys,
values and complete observations. A supplied assertion that a trace is correct
does not make it pass.

An external adapter can supply the same trace schema from an actual system,
with a separately documented execution context and evidence. Running the
checker on literal examples establishes only checker behavior. Authentication,
persistence, process replacement and recovery remain unexecuted system tests.

## Testing and failure receipts

The test command emits `hippo-eval-test-receipt/v2`. `PASSED` requires discovered
files, discovered cases, at least one executed test, no failures/errors and
unchanged source/test identities. `DISCOVERY_FAILED`, `ZERO_TESTS_EXECUTED`,
`TEST_FAILURES` and `SOURCE_CHANGED` identify different failure states.

Comparison outputs are retained even when the command exits unsuccessfully.
Inference claim lifecycle tests cover live owners, abandoned owners, PID reuse,
zombie ownership, ambiguous state and deterministic finally cleanup. These
are evaluator reliability tests, not production-system security certification.
