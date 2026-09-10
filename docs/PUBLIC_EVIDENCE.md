# Evidence identities and export transformations

This release candidate separates an earlier experiment, the standalone export,
and new release-validation runs. New results identify their generating source
files, software commit when available, fixtures, configuration, dependency
versions, interpreter hash, and model artifact hashes.

The public retrieval fixture is `synthetic-workspace-stories-v2-public1`.
Its 300 record objects and 188 query objects, including searchable text,
applicability rules, relevance grades, rationales, and exact body hashes, are
unchanged from the final earlier experiment. Only top-level authorship and
version metadata were revised to describe this standalone distribution. That
changes the full fixture identity. The export is not byte-identical historical
input, and the historical result bundle is not represented as its output.

The earlier experiment compared four declared development configurations before
scoring its query holdout: 128 or 240 tokens, lexical fusion weight 1 or 2,
32-token overlap, semantic weight 1, and RRF constant 60. Mean answerable
development nDCG@10 across the four semantic/hybrid methods controlled selection.
Differences within 0.005 used fewer chunks, then lexical weight 1, as tie breaks.
The selected configuration was 240 tokens and equal weights. Both models and
all documents were already available; only held-out query scoring was withheld.

The standalone re-evaluation uses that established configuration without a new
selection. The historical held-out queries are now known. These runs measure
reproduction on known inputs, not fresh blinded generalization. Compatibility
guards remain active. Historical and public full fixture envelopes differ;
ordinary regression comparison must reject that pair rather than invent a
cross-identity score delta. A private provenance audit checked the unchanged
record/query arrays and independently recomputed earlier metrics. This release
uses its own public raw measurements as the support for numerical claims.

The scenario examples are a separately versioned public derivative. Private
planning cross-references were removed. A product-specific policy example was
replaced by a generic editorial review/publication case, and shared-record
terminology and model authorship were made explicit. The 12 cases and 35 steps
test the checker; they do not publish a product specification or prove that a
running system produced the supplied traces. Neither altered scenario bytes
nor new receipts are called unchanged historical evidence.

The retained `hippo_eval` Python namespace and `hippo-*` schema tokens are
compatibility identifiers. They do not change the public software identity or
grant authority to any fixture or observation. Renaming these protocol tokens
would create avoidable incompatibility without changing the experiment.

The later editorial revision changes presentation and author metadata, not the
record/query objects, configurations, acquisition pins, evaluator implementation,
or raw observations. Its report tables are regenerated from the same bound
bundles. Earlier measurement and validation receipts keep their original
identities; new editorial and archive checks are identified separately in the
[results ledger](../results/README.md). A new report render is not a new retrieval
experiment, and the historical query holdout is not newly blinded.
