# Dataset and result identities

The earlier experiment, standalone dataset and reproduction runs have separate
identities. Results identify their generating source files, software commit when
available, dataset, configuration, dependency
versions, interpreter hash, and model artifact hashes.

The dataset version is `synthetic-workspace-stories-v2-public1`.
Its 300 record objects and 188 query objects, including searchable text,
applicability rules, relevance grades, rationales, and exact body hashes, are
unchanged from the final earlier experiment. Only top-level authorship and
version metadata were revised to describe this standalone distribution. That
changes the full dataset identity. Results generated from that version are
recorded separately from the earlier experiment.

The earlier experiment compared four declared development configurations before
scoring its query holdout: 128 or 240 tokens, lexical fusion weight 1 or 2,
32-token overlap, semantic weight 1, and RRF constant 60. Mean answerable
development nDCG@10 across the four semantic/hybrid methods controlled selection.
Candidates within 0.005 of the best objective were ordered by the total BGE and
MiniLM indexed chunks, then lower lexical weight, then configuration digest.
The selected configuration was 240 tokens and equal weights. Both models and
all documents were already available; only held-out query scoring was withheld.

The standalone re-evaluation uses that established configuration on known query
splits. Because the complete dataset metadata differs, ordinary regression
comparison rejects the historical/standalone pair on `identity.fixture_digest`.
The report's numerical claims use the retained standalone raw measurements in
the [results ledger](../results/README.md).

The scenario examples form a separately versioned dataset with 12 cases and
35 steps per trace set. They include a generic editorial review/publication
case. Correct and deliberately incorrect observations test the checker; they
are distinct from the earlier scenario data and from external-system output.

Report tables are generated from the identified result bundles. Each measurement and validation record
describes its own inputs and execution; rebuilding a report reuses existing
rankings.
