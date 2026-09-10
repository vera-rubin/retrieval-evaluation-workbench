# Version 1.0.0

This version includes five retrieval configurations: SQLite FTS5 BM25,
BGE-small-en-v1.5, all-MiniLM-L6-v2, and two lexical/semantic combinations
using reciprocal-rank fusion.

The distribution contains:

- 300 synthetic records and 188 labeled queries, with filtering rules and
  development/held-out splits;
- retrieval, complete-record, result, and scenario checks, including a
  171-test evaluator suite and twelve pairs of correct/incorrect traces;
- machine-readable observations, per-query reports, comparison tools, and
  separate arithmetic and tokenizer-inspection utilities;
- pinned dependency/model acquisition, fixed-configuration reproduction
  commands, and an adapter interface for other retrieval implementations;
- the technical report, editable source, HTML/PDF, and generated tables/figure.

The tested platform is Windows x64 with CPython 3.13.15. Inference runs locally
on the CPU. Model weights and dependency binaries are acquired separately;
the source distribution includes their identities and notices.

The recorded comparison uses small, related synthetic projects and known query
splits. Timing and sampled memory observations come from one host. See the
[report](report/report.html) for findings and limitations, the
[installation guide](docs/INSTALLATION.md) for resource requirements, and
[verification records](docs/VERIFICATION.md) for the checks performed.
