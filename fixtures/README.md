# Synthetic retrieval dataset

The evaluation inputs are `corpus.json` and `queries.json`.
The six `cases_*.py` files contain readable story specifications;
`build_fixtures.py` deterministically generates the JSON and `audit.json`.
The generator uses the story specifications and does not read retrieval results.

The corpus contains 300 records in 30 story families and 188 queries. There are
94 development queries and 94 queries in the original held-out split, with
fifteen families assigned to each. Both splits use the same 300-record corpus;
the 291 records with retained bodies are indexed, and each query ranks only
eligible records. The original split withheld query scoring and relevance use
during configuration selection, while all documents were available for indexing.
The held-out split is now known, so new executions are reproductions or re-evaluations.

## Construction and review

The stories, identifiers, people, code references and labels describe fictional
projects. Labels follow the record text and explicit query rules. The report's
[Construction and review](../report/report.html#construction-and-review) section
describes dataset generation and the tools used for review.

A review covered twenty of 188 queries against their records and rules before
the first full comparison, without retrieval scores: ten development and ten
held-out queries. It found two missing
grade-1 illustrations. The Orchard trial illustrates the rain rule in its
combined quota/rain question; the Tide revised-sailing observation illustrates
the twelve-minute boarding deadline. These labels and rationales were corrected
from the text before scoring. No engine scores informed those corrections.

The authoring process could see both splits, and scenario types recur across
them. The twenty-query review was a sample, not an exhaustive relevance assessment.

## Searchable text and relevance

Only record title and body are searchable. Query/record IDs, family labels,
relevance mappings, rationales, authorship fields and applicability rules must
not be appended to indexed or embedded text. Body SHA-256 values bind exact UTF-8
bytes. Code paths and provenance source IDs refer to invented story-world
material. A `verified` field is a status assigned within a story.

- Grade 3 directly answers a query or an independently requested component.
- Grade 2 supplies an explicit partial answer or corroboration.
- Grade 1 supplies useful illustration or context without establishing the answer.
- An omitted ID is nonrelevant or ineligible under the query's explicit rules.

Recall, precision and reciprocal rank treat grades 1–3 as relevant. nDCG uses
their graded gains. Relevance is judged at the record-ID level; embedding
similarity is the ranker's score, not a separate relevance label. Multiple
relevant records may supply distinct answer components, but the evaluator does
not test whether a downstream system synthesizes them correctly.

Each split contains 79 answerable queries and fifteen unanswerable requests.
Quality averages use the answerable queries. Unanswerable requests have empty
relevance sets and are reported separately. The convention asks whether a record
establishes a positively requested claim. Some retained counterevidence is
therefore counted as a false retrieval even though it could help an answerer
reject a false premise. Returned candidates are not generated answers, and this
dataset does not measure hallucination or an answerability threshold.

## Applicability and coverage

Ordinary queries search one of six declared synthetic workspaces, each with five
related projects and their authors. Tasks are unrestricted unless a query
explicitly selects one. Other queries restrict owners, status, epistemic state,
revision or evidence availability. Eligibility is applied separately from
similarity ranking. These are dataset filters, not authentication checks.

The schemas are `hippo-corpus/v1` and `hippo-queries/v1`. Levels 1, 2 and 3 label
episodes/facts, private preferences/syntheses, and shared decisions respectively.

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

## Validation and dataset version

Dataset validation checks schema and field types, exact body hashes, duplicate
IDs, duplicate query text plus rules, relevance eligibility, broken references,
supersession cycles, contradictory source availability, embedded oracle IDs,
declared family leakage and exact-text cross-split leakage. Near-duplicate token
overlap is advisory. The audit catches structural problems; interpreting label
quality and semantic overlap requires examining the records and queries.

The dataset version is `synthetic-workspace-stories-v2-public1`. It changes
only the dataset version and authorship metadata of the original final inputs.
All record and query objects, searchable text, rules, rationales and relevance
labels are preserved. The complete dataset digest consequently differs from the
earlier metadata. See [dataset and result identities](../docs/PUBLIC_EVIDENCE.md)
for the relationship between these versions and their measurements.

The [scenario data](../scenarios/cases.json) are versioned separately. Their paired
correct and incorrect traces test exact comparison of supplied observations.
