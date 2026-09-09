# Connecting another retrieval implementation

The `RetrievalAdapter` protocol in `hippo_eval/contracts.py` provides
`build(records, config)`, `search(query, eligible_ids, k)`, `fetch(record_id)`,
`identity`, and `close()`. Implementations return actual observations rather
than oracle labels. `create_engine` in `hippo_eval/retrieval.py` selects the
built-in implementations; a future adapter can be added there with its own
identity and tests.

`build` records setup/index measurements. `search` returns unique record IDs,
finite scores, and optional exact chunk provenance. `fetch` returns a full
independent copy of the canonical input record, preserving body and provenance.
The supplied eligible-ID set is a synthetic test constraint. It is not an
authenticated capability or a substitute for an implementation's authorization.

Results distinguish executed, failed, and not-run methods and OK, error, and
unavailable queries. Missing evidence and incomplete output must remain
explicit. Configuration, source, fixtures, dependencies, models and supervised
resource receipts bind observations. The evaluator recomputes scores from raw
results instead of trusting embedded analyses. Do not disable these guards to
make an incompatible adapter look comparable.

The scenario checker accepts explicitly synthetic finite JSON traces. It checks
supplied values against literal expectations and does not drive a real system.
Testing authenticated identity, transaction durability, process replacement,
or recovery requires a separately supplied implementation and authorized test
driver. No final transport or product API is assumed here.
