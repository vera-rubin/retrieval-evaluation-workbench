# Reproducible Retrieval Evaluation

## A Workbench for Lexical, Semantic, and Hybrid Search

Nathan Chandrasekar

[ORCID 0009-0003-9702-8164](https://orcid.org/0009-0003-9702-8164)

Technical report accompanying proposed software version 1.0.0. Release candidate for review.

### Abstract

I compare lexical, semantic, and hybrid retrieval over synthetic project records: how do ranking quality, recall, and query latency differ under shared eligibility rules? I built a standalone workbench that makes the comparison reproducible and its observations inspectable. It evaluates SQLite FTS5 BM25, BGE-small-en-v1.5, all-MiniLM-L6-v2, and two equal-weight reciprocal-rank-fusion hybrids using 300 records and 188 labeled queries. Of 291 indexed records, each query ranks an eligible pool of 1-43 records (median 36), excluding null bodies and applying its scope/status rules. The report uses an established configuration on both known query splits, without retuning or changing labels. On the 79 answerable held-out queries, BGE obtains nDCG@10 of 0.9588 and recall@10 of 0.9831; MiniLM obtains 0.9379 and 0.9863; lexical recall is 0.9363. The hybrids do not consistently improve over their semantic components. A repeat preserves every quality aggregate while query timings change materially. All five methods returned candidates for the fifteen empty-relevance queries; successful semantic/fusion searches return candidates when eligible indexed passages exist. No answerability decision rule was evaluated.

## 1. Contribution and retrieval task

Retrieval comparisons are difficult to interpret when eligibility, truncation, labels, or failure handling differ between methods. A plausible ranked list can conceal an ineligible record, incomplete evidence, or an execution that never occurred. I make those conditions visible alongside retrieval scores.

The task is to retrieve relevant records about fictional project facts, decisions, preferences, observations, and code references. Queries can request current or historical evidence, distinguish same-name entities, or require several records. Both splits use the same corpus; each query ranks only its eligible records, rather than all 300 fixture objects.

The contribution is the evaluation software and documented comparison, not a new ranking algorithm. The workbench combines versioned fixtures, interchangeable retrieval adapters, complete-record checks, result-contract validation, compatible-run comparison, and static reports. A future implementation can supply observations through the same adapter boundary. The source distribution includes the code, pinned acquisition recipes, tests, raw observations, and this report.

<!-- pagebreak -->

## 2. Fixtures and applicability

The corpus contains thirty synthetic story families with ten records each. Its 300 records comprise 253 current, 29 superseded, seven disputed, two revoked, and nine deleted records. The nine deleted records have null bodies: their metadata remains in the fixture, but neither their title nor body is indexed. Each method indexes the same 291 retained-body records.

The 188 queries form development and original held-out splits of 94 queries from fifteen families each. Each split has 79 answerable queries and fifteen with empty relevance sets. The original split withheld query scoring and relevance use during configuration selection; documents from both splits were available for indexing. The held-out queries are now known.

### Construction and bounded review

OpenAI Codex generated the stories, identifiers, code references, records, queries, and labels; they do not represent a real project corpus. Before the original full comparison, a second model-assisted reviewer inspected 20 of 188 queries, ten per split, against their records and rules without retrieval scores. That bounded review found two missing grade-1 illustrations: an Orchard rain-rule trial and a Tide boarding-deadline observation. The labels and rationales were corrected from the text before scoring. This review supplies neither an overall label-error rate nor a direction of metric bias. It was not a human annotation study or exhaustive relevance assessment.

### Relevance and eligibility

Grade 3 directly answers a query or an independently requested component. Grade 2 supplies an explicit partial answer or corroboration. Grade 1 supplies useful illustration or context without establishing the answer. An omitted record is nonrelevant or ineligible under the query's rules. Labels attach to record IDs, not embedding neighborhoods; each query includes a reviewable rationale.

Ordinary queries select one of six synthetic workspaces, each containing five related projects and their authors. Other rules constrain project, task, owner, status, epistemic state, revision, or evidence availability. Eligibility is computed before ranking. The shared-owner and verified-status fields describe fictional judgments, not authenticated authority.

### Coverage and candidate pools

Thirty questions request multiple records; six target trial observations; six target evidence in the final paragraph of bodies longer than 1,000 characters. Coverage also includes unsupported hypotheses, supersession, disagreement, preferences, and missing or deleted evidence.

Eligible pools, computed after rejecting null bodies and applying each query's rules, have minimum, median, and maximum sizes of 1, 36, and 43 across all 188 queries. Fifty of 158 answerable queries have at most ten eligible records, 25 per split. I retain all queries in the primary analysis and describe the larger-pool subset alongside the results. Repeated story structure and a shared authoring process limit the independence of the query families.

Only title and body are searchable. IDs, labels, rationales, family assignments, and rules remain evaluator metadata. Mechanical audits cover all fixtures for references, body hashes, duplicate cases, eligibility contradictions, supersession cycles, and declared split leakage. They are distinct from the 20-query relevance review and do not establish semantic independence or factual truth.

<!-- pagebreak -->

## 3. Retrieval methods and metrics

### Shared retrieval contract

Each method builds an experimental index from the same records, searches a supplied eligible-ID set, and fetches the full canonical fixture record for every returned hit. Search results are deduplicated at record level. Ties are resolved by stable record ID. Original UTF-8 bodies remain unchanged: exact returned bodies, provenance, fields, and revision/status observations are compared with the fixture. A matching hash establishes byte fidelity, not relevance or truth.

**Lexical.** APSW 3.53.4.0 links SQLite 3.53.4. FTS5 indexes title and body using unicode61 tokenization. Literal Unicode query terms are joined with OR; user text is not executed as FTS syntax. BM25 ranks matching records with whole-corpus statistics, with eligibility restricted before ordering and limiting. FTS5's documented BM25 score uses lower values for better matches [1]. The adapter exposes the corresponding descending score convention.

**Semantic.** Both models produce 384-dimensional, L2-normalized vectors. BGE-small-en-v1.5 uses CLS pooling and its documented query-only retrieval instruction [2]. MiniLM uses attention-mask mean pooling and no query prefix [3]. Their maximum sequence lengths are 512 and 256 tokens respectively. Inference uses local immutable artifacts, float32, CPU execution, batches of eight, and at most two compute threads. The loader calls torch.manual_seed(17); forward passes use eval mode and torch.inference_mode(). This does not establish cross-host determinism or seed irrelevance. It does not load remote custom model code.

Title and body are chunked separately with each model's fast tokenizer, a 240-token budget including special tokens, and 32-token overlap. Every substring is retokenized to verify the limit. Character and UTF-8 byte offsets bind passages to retained text; no full record is silently truncated. A separate pinned-tokenizer inspection confirms each model's 588 chunks: 576 one-chunk fields and six two-chunk bodies, with no split titles. This corpus exercises only two chunks per field at most; focused chunking tests use a tokenizer double and do not demonstrate model inference. Query limits include the instruction prefix and special tokens; overlong queries fail explicitly. Search scans normalized vectors with NumPy dot products after eligibility filtering, then takes the best passage score per record. This is exact cosine scanning, not a production sqlite-vec service.

**Hybrid.** Each hybrid sums reciprocal ranks, 1 / (60 + rank), with one-based ranks and equal component weights [4]. It requests len(eligible_ids) results from each component before taking the final top ten. Semantic search contributes every eligible record with indexed passages; lexical search contributes only term matches. A lexical nonmatch receives no lexical RRF term. Input bounds for these paths are in the [interface guide](../docs/INTERFACES.md#bounds-of-the-bundled-implementations).

### Metric definitions

Recall@10, precision@10, and MRR@10 treat grades 1-3 as relevant. Recall divides hits by the number of gold records; precision divides by ten even when fewer hits return. MRR is the reciprocal rank of the first relevant hit within ten. nDCG@10 uses gain 2^grade - 1, a log2(rank + 1) discount, and the ideal top-ten label ordering.

The four quality metrics are macro means over 79 answerable queries per split. The fifteen empty-gold queries enter separate unanswerable diagnostics. Explicit error or unavailable responses in an otherwise executed method score as empty retrieval. Malformed result contracts invalidate aggregates; a wholly unexecuted method has no score. This avoids improving a method by silently dropping its failed requests.

<!-- pagebreak -->

## 4. Fixed-configuration protocol

The retained executions use a 240-token chunk budget, 32-token overlap, equal fusion weights, RRF constant 60, k=10, and seed 17. The earlier four-configuration selection used mean answerable development nDCG@10 across the two semantic and two hybrid methods; FTS5 was outside the objective. Its declared tie-break procedure is in the [evidence lineage](../docs/PUBLIC_EVIDENCE.md). It did not establish an optimal configuration.

I report the existing development re-evaluation, primary held-out re-evaluation, and held-out repeat. The original held-out queries were already known. No configuration or label was changed for this editorial revision, and no model benchmark was rerun. The primary pass remains primary even though the repeat was faster. Tables and the figure are regenerated from the same raw observations; Appendix A records their identities.

## 5. Retrieval quality

The primary held-out pass executed 470 method/query searches. Table 1 averages the 79 answerable held-out queries for each method; the fifteen empty-relevance queries enter separate diagnostics. All three retained runs passed result-contract validation.

**Table 1. Primary held-out results, 79 answerable queries.**

{{QUALITY_TABLE}}

{{QUALITY_FIGURE}}

Held-out mean precision@10 can reach 158 / (79 x 10) = 0.2000: there are 158 relevant record-query assignments and at most five gold records per query. Precision divides by ten even for shorter lists; the ceiling assumes all labeled records are retrieved.

BGE has the highest nDCG and MRR; MiniLM has slightly higher macro recall. They retrieve 153 and 154 relevant record-query hits respectively. That net difference does not identify how many queries differ, and macro recall weights queries equally rather than pooling hits. Both exceed lexical recall. FTS+BGE trails BGE on all four metrics; FTS+MiniLM improves on MiniLM only in nDCG.

<!-- pagebreak -->

### Development, repetition, and larger pools

Development is a re-evaluation of known inputs whose nDCG previously informed configuration selection, not a neutral selection holdout or a new tuning opportunity. Its 170 relevant record-query assignments across 79 answerable queries, at most five per query, give a precision@10 ceiling of 170 / 790 = 0.21519.

**Table 2. Development results, 79 answerable queries.**

{{DEVELOPMENT_TABLE}}

The held-out repeat preserves every quality aggregate. A new [separate arithmetic check](../results/validation/arithmetic-source-review.json), executed on 10 September 2026 UTC over all three retained runs, agreed within 1e-12 without importing evaluator metrics. It checks formulas on known ranks, not new retrieval execution, independent samples or statistical significance.

On the 25 answerable held-out queries with pools no larger than ten, semantic/hybrid recall is structurally one: all eligible records have indexed passages and fit within k. Lexical still requires term matches; its recall of one is observed. Ideal nDCG of one is observed for all five methods, not implied by pool size. Table 3 describes the other 54 queries by existing pool size; all 79 remain primary. Relative recall and nDCG ordering is unchanged.

**Table 3. Descriptive held-out subset with more than ten eligible candidates.**

{{POOL_TABLE}}

### Concrete misses and empty-relevance queries

The Slate import question requests column order and preview headings. Both semantic methods retrieve the two grade-3 direct records but miss two grade-2 corroborating records within ten: recall is 0.5, MRR is one, and nDCG is 0.8035. The requested facts are present despite the incomplete supporting set. Per-query grades and ranks expose that distinction.

The Violet identifier question misses the warmup record under both semantic methods, giving recall of two thirds; lexical also misses the reference record, giving one third. For the Orchard paraphrase, both hybrids miss a trial record retrieved by both semantic-only methods. Fusion can move useful evidence out of the top ten.

All five methods returned candidates for the fifteen empty-relevance queries in each run. Successful semantic/hybrid search with positive k returns candidates when eligible indexed passages exist; missing artifacts, failed encoding and empty indexed pools are separate cases. No answerability rule was evaluated. The separate empty-gold diagnostics count nonempty lists as false retrievals, even when counterevidence could reject a query's premise. They do not enter the primary quality means or measure generated-answer hallucination.

<!-- pagebreak -->

## 6. Runtime and resource observations

Measurements came from one Windows x64 host using CPython 3.13.15, PyTorch 2.9.1+cpu, Transformers 4.57.1, tokenizers 0.22.1, and NumPy 2.3.4. The 29-wheel lock and immutable model revisions define acquisition. Each run used one owned inference process; host scheduling, file-page state, and other system load were not controlled.

**Table 4. Setup and indexing, one observation per method in the primary held-out process.**

{{SETUP_TABLE}}

The semantic load timer includes record validation, artifact verification and deferred torch/transformers imports; the first semantic engine encounters framework imports that later engines reuse. Index time includes tokenization and passage encoding; each hybrid sums two real component builds. All three passes ran lexical, BGE, MiniLM, hybrid BGE, then hybrid MiniLM. These are not independently cold model starts, and a faster later build alone does not identify a defect or a timing cause.

**Table 5. Primary held-out (First) and repeat warm latency, ms; 94 requests per method/pass.**

{{LATENCY_TABLE}}

Warm latency covers successive distinct requests after index construction. p50 is the median; p95 is the nearest-rank 95th percentile. It includes eligibility construction, query encoding/search, full-record fetch, and fidelity hashing, but excludes index setup and answer generation.

The primary held-out worker took 60.496 seconds and its repeat 34.159 seconds. Quality stayed fixed while latency and elapsed runtime changed. The existing observations do not isolate a cause for differences between development, held-out, or repeat runs. Lexical had the lowest query latency, and MiniLM had lower query latency than BGE in both held-out passes. A later hybrid median below its semantic component's does not establish that fusion accelerates encoding.

**Table 6. Whole-worker sampled memory and elapsed runtime.**

{{RESOURCE_TABLE}}

The semantic path samples RSS after load and each encode batch, aborting above 2 GiB. The supervisor polls every 100 ms and terminates the owned worker on sampled RSS excess or the 900-second bound. These are not OS allocation limits. All runs exited zero without recorded resource failure; sampled maxima stayed below 490 MiB. No monetary cost or energy consumption was measured.

<!-- pagebreak -->

## 7. Fidelity checks and evaluator validation

The primary held-out pass performed 3,843 complete-record fetch checks: 723 lexical and 780 for each semantic/hybrid method. Body, provenance, complete-record, synthetic scope, owner, status, and revision mismatch counts were zero. These checks concern retained fixture fidelity; a correctly fetched record can still be irrelevant.

The evaluator suite contains 171 tests. The [pre-commit editorial checkout receipt](../results/validation/editorial-171.json) executed them with zero skips, failures or errors and binds unchanged evaluator/test file hashes; its observed HEAD is not the later edited commit. Separately, the [93-file archive of 5e71d766](../results/validation/archive-5e71d766.json) executed 171 tests, fixtures and twelve trace pairs, and rebuilt all report outputs identically using reused local dependencies. It ran no separate retrieval benchmark. The earlier 164-test clean archive acquired assets and ran 94 lexical queries; it did not run semantic inference. The current final archive is checked separately in the approval package. Each event retains its own identity in the [validation ledger](../results/README.md).

There are twelve scenario cases, each supplied with a correct trace and a deliberately incorrect trace: two variant sets covering the same twelve cases and 35 steps per set. The checker accepted all twelve correct variants and rejected all twelve incorrect variants. These are not 24 independent scenarios or observations from a deployed system.

The retained validation also includes a missing-dependency probe that exited nonzero, reported APSW_NOT_STAGED and NOT_RUN, and emitted no query observations. Unmatched smoke discovery failed. Regression tests cover comparison failures with reports retained, empty or wholly unexecuted test selections, nondefault artifact-root bootstrap, and live, stale, or ambiguous inference-lock ownership. Their outcomes are finite software checks, not universal guarantees.

## 8. Limitations

The fixtures are clean English, model-authored stories with short invented code references, not human-validated judgments or real project corpora. Thirty related templates, sparse labels, small pools, and shared authorship limit generalization. Documents were available across both query splits, and the original held-out queries were already known at re-evaluation. The bounded model-assisted label review was not academic peer review or independent experimental validation.

The task measures candidate retrieval and fixture fidelity. It does not test answer synthesis, truth, authenticated cross-owner authority, durable ingestion, live session replacement, power-loss recovery, or containment. Supplied traces test the checker against literal expectations. Published model-card benchmarks do not establish results on this corpus. Timing and RSS are local observations from one host; other platforms and deployment workloads remain unqualified.

## 9. Conclusion

Within this fixed experiment, BGE has the highest held-out nDCG@10 and MRR@10. MiniLM has slightly higher recall@10 and lower observed query latency than BGE in both held-out passes. The two tested equal-weight hybrids do not consistently improve on their semantic components. The workbench makes these differences inspectable through pinned inputs, raw observations, record checks, and executable evaluation contracts. The shared synthetic setting and its labels bound the conclusions.

<!-- pagebreak -->

## 10. Reproduction and evidence lineage

The source distribution includes evaluator/adapters, fixture generators and JSON, tests, pinned acquisition recipes, raw gzip bundles, static per-query reports, and this editable manuscript and builder. Model weights and dependency binaries are acquired separately. The supported initial target is Windows x64 with CPython 3.13.

Two reproduction targets are distinct. Rescoring retained bundles and rebuilding this report reuse existing rankings without inference; re-executing retrieval creates new observations with staged models. The [installation guide](../docs/INSTALLATION.md) gives both paths. Use new output directories and declarations for changed inputs. The [results ledger](../results/README.md), [verification notes](../docs/VERIFICATION.md), and [report build guide](BUILD.md) identify receipts, arithmetic/tokenizer checks and automatic table generation. Neither same-host repetition nor retained-rank agreement proves identical results or timings on another host.

The retained hippo_eval namespace and schema tokens are compatibility identifiers. Adapters expose build, search, fetch, and close operations and report their identities; no final product transport or authority service is assumed.

### Appendix A. Evidence identities

The earlier experiment, standalone export, and release-validation runs have separate identities. The public fixture preserves all record/query objects while changing its descriptive envelope; the generic trace scenarios are a versioned derivative. Retained runs record their generating commit, source-file hashes, fixture/configuration/dependency digests, interpreter, and model manifests. The editorial revision does not replace those identities.

The recorded historical/export comparison rejects specifically on identity.fixture_digest. The code compares the complete fixture digest; it does not separately reject fields named version or authorship. The earlier provenance inspection established unchanged record/query objects and matching ranked lists. That does not make the two full fixture identities compatible. The report's numerical support remains the retained public raw observations below.

{{MEASUREMENTS_ID}}

### References

[1] SQLite Project. [FTS5 extension and BM25 auxiliary function](https://www.sqlite.org/fts5.html#the_bm25_function). Official implementation documentation.

[2] BAAI. [bge-small-en-v1.5 model card, revision 5c38ec7](https://huggingface.co/BAAI/bge-small-en-v1.5/blob/5c38ec7c405ec4b44b94cc5a9bb96e735b38267a/README.md). CLS pooling, normalization, and retrieval instruction. Exact revision and downloaded artifact hashes are recorded by the workbench.

[3] Sentence Transformers. [all-MiniLM-L6-v2 model card, revision 1110a24](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/blob/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/README.md). Mean pooling, normalization, and sequence-length configuration.

[4] Gordon V. Cormack, Charles L. A. Clarke, and Stefan Buettcher. [Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf). SIGIR, 2009. The present work applies reciprocal-rank fusion and does not reproduce that paper's experiments.

### Tooling and responsibility

AI use: OpenAI Codex assisted software development, synthetic-fixture and label generation, analysis, review, visualization code, and manuscript preparation; Anthropic Claude assisted editorial review and revision. I retain responsibility for the approved published content.
