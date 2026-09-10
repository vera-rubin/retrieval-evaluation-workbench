# Connecting another retrieval implementation

The `RetrievalAdapter` protocol in `hippo_eval/contracts.py` provides
`build(records, config)`, `search(query, eligible_ids, k)`, `fetch(record_id)`,
`identity`, and `close()`. Implementations return observed search and fetch
results. `create_engine` in `hippo_eval/retrieval.py` selects the
built-in implementations; another adapter can be added there with its own
identity and tests.

`build` records setup/index measurements. `search` returns unique record IDs,
finite scores, and optional exact chunk provenance. `fetch` returns a full
independent copy of the input record, preserving body and provenance.
The supplied eligible-ID set applies dataset filters; an external implementation
must handle its own authentication and authorization.

Results distinguish executed, failed, and not-run methods and OK, error, and
unavailable queries. Missing evidence and incomplete output must remain
explicit. Configuration, source, dataset, dependency, model and resource records
identify each run. The evaluator recomputes scores from raw observations and
checks compatibility before comparing two runs.

The scenario checker accepts finite JSON traces and compares their values with
literal expectations. A test driver supplies observations from an external system with a documented
execution context; the checker evaluates those observations against the expected
values.
