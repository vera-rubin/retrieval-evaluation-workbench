# Synthetic retrieval fixtures

The materialized evaluation inputs are `corpus.json` and `queries.json`.
The six `cases_*.py` files contain readable story specifications;
`build_fixtures.py` deterministically generates the JSON and `audit.json`.
The generator does not inspect retrieval results or change labels to match a
search method.

The corpus contains 300 records in 30 story families and 188 queries. There are
94 development queries and 94 queries in the original held-out split, with
fifteen families assigned to each. Both splits use the same 300-record corpus;
the 291 records with retained bodies are indexed, and each query ranks only
eligible records. The split withholds query scoring and relevance use for configuration
selection; it does not hide documents from indexing. The original held-out split
is now known, so publication executions are reproductions or re-evaluations.

## Construction and review

OpenAI Codex generated the stories, identifiers, paths, people, source references,
records, queries and relevance labels as synthetic material. The fixture
construction used no real project corpus. Labels follow the authored text and
explicit scope rules. They have not been validated by human annotators.

A second model-assisted reviewer inspected twenty of 188 queries against their records
and rules before the first full comparison, without retrieval scores: ten
development and ten held-out queries. This bounded review found two missing
grade-1 illustrations. The Orchard trial illustrates the rain rule in its
combined quota/rain question; the Tide revised-sailing observation illustrates
the twelve-minute boarding deadline. These labels and rationales were corrected
from the text before scoring. No engine scores informed those corrections.

Family separation is not an independently blinded benchmark. The authoring
process could see both splits, and scenario types recur across them. The review
does not establish exhaustive relevance judgments or human annotation quality.

## Searchable text and relevance

Only record title and body are searchable. Query/record IDs, family labels,
relevance mappings, rationales, authorship fields and applicability rules must
not be appended to indexed or embedded text. Body SHA-256 values bind exact UTF-8
bytes. Code paths and provenance source IDs refer to invented story-world
material, not actual source files. A `verified` field records a fictional
judgment; it is not an authenticated verification receipt.

- Grade 3 directly answers a query or an independently requested component.
- Grade 2 supplies an explicit partial answer or corroboration.
- Grade 1 supplies useful illustration or context without establishing the answer.
- An omitted ID is nonrelevant or ineligible under the query's explicit rules.

Recall, precision and reciprocal rank treat grades 1–3 as relevant. nDCG uses
their graded gains. Relevance is judged at the record-ID level; embedding
similarity is the ranker's score, not a separate relevance oracle. Multiple
relevant records may supply distinct answer components, but the evaluator does
not test whether a downstream system synthesizes them correctly.

Each split contains 79 answerable queries and fifteen unanswerable requests.
Quality averages use the answerable queries. Unanswerable requests have empty
gold sets and are reported separately. The convention asks whether a record
establishes a positively requested claim. Some retained counterevidence is
therefore counted as a false retrieval even though it could help an answerer
reject a false premise. Returned candidates are not generated answers, and this
fixture does not measure hallucination or an answerability threshold.

## Applicability and coverage

Ordinary queries search one of six declared synthetic workspaces, each with five
related projects and their authors. Tasks are unrestricted unless a query
explicitly selects one. Other queries restrict owners, status, epistemic state,
revision or evidence availability. Eligibility is applied separately from
similarity ranking. Successful synthetic filtering is not proof of real access
control.

The fixture retains its stable schema identifiers, including `hippo-corpus/v1`
and `hippo-queries/v1`, for compatibility. The fictional owner name `Hive` denotes
shared story-world decisions. These identifiers do not name a released product
or confer authority. Levels 1, 2 and 3 label synthetic episodes/facts, private
preferences/syntheses, and shared verified decisions respectively.

Coverage includes identifiers, paraphrases, code references, preferences,
decisions, observed trials, unsupported hypotheses, old/current/revoked revisions,
supersession, disagreement, same-name entities, project/task distinctions,
multi-record questions, missing evidence and deleted payloads. Thirty questions
request multiple records. Six questions target observed trials, and six target
late evidence in long bodies. The long bodies exceed 1,000 characters and place
their decisive material in the final paragraph. They contain investigation
context rather than repeated padding.

There are 253 current, 29 superseded, seven disputed, two revoked and nine deleted
records. The nine deleted records have no body; 291 records can be indexed.
Eligible-set sizes, computed after rejecting null bodies and applying each
query's rules, have minimum/median/maximum 1/36/43. Fifty of 158 answerable
queries have at most ten eligible records, 25 per split. Top-ten recall is
potentially trivial for those cases. The remaining 108 answerable queries have
more than ten eligible candidates. Inspect the per-query audit and pool-stratified
analysis when interpreting retrieval discrimination.

The corpus is structured and deliberately small. Every family has ten records,
most have an old/current contrast, and each has an unanswerable request. Documents
are clean English prose with short invented code references, not noisy chat
histories, real code repositories, multilingual data or an exhaustive adversarial
workload. Template similarity, sparse labels and small pools limit generalization.

## Validation and publication identity

Fixture validation checks schema and field types, exact body hashes, duplicate
IDs, duplicate query text plus rules, relevance eligibility, broken references,
supersession cycles, contradictory source availability, embedded oracle IDs,
declared family leakage and exact-text cross-split leakage. Near-duplicate token
overlap is advisory. These checks do not establish semantic independence,
external source existence, access-control correctness or factual truth.

The publication version is `synthetic-workspace-stories-v2-public1`. It changes
only the descriptive version/authorship envelope of the original final inputs.
All record and query objects, searchable text, rules, rationales and relevance
labels are preserved. The complete fixture digest consequently differs from the
historical envelope; release-validation results bind the publication fixture
identity. Historical scores must not be relabeled as executions of this export.

The generic supplied-trace scenarios are a separate, explicitly versioned
derivative. They test exact result/trace comparison, including deliberately
incorrect observations. Their success does not demonstrate a storage engine,
authenticated service, persistence, session replacement or recovery system.
