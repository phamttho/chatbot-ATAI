# Capability update results

The updated and previous systems use Qwen 3.5 4B; baseline is the original Qwen 2.5 1.5B system. The update changes title retrieval, structured query planning, graph property exposure, and validated query compilation.

The original quality suite is a regression suite. The 47-case capability extension contains three supplied examples and 44 additional graph-derived cases selected before inference. All new complete gold sets were independently verified with RDFLib. These are coverage tests, not a production accuracy estimate.

| Metric | baseline | previous | updated |
|---|---:|---:|---:|
| Original factual suite | 73/96 (76.0%) | 90/96 (93.8%) | 96/96 (100.0%) |
| Original guardrail suite | 61/100 (61.0%) | 90/100 (90.0%) | 90/100 (90.0%) |
| Capability extension | 12/47 (25.5%) | 6/47 (12.8%) | 46/47 (97.9%) |
| Supplied three regressions | 0/3 | 0/3 | 3/3 |
| Additional capability cases | 12/44 | 6/44 | 43/44 |

Split rows are subsets of the capability extension, not additional tests. Guardrail success requires exact labels and correct handling; refusal handling is also reported independently in the JSON summaries.

| Capability group | baseline | previous | updated |
|---|---:|---:|---:|
| article_title | 0/7 | 0/7 | 6/7 |
| count_cast | 6/6 | 0/6 | 6/6 |
| count_tags | 0/7 | 0/7 | 7/7 |
| lookup_rating | 0/6 | 0/6 | 6/6 |
| lookup_tags | 0/6 | 0/6 | 6/6 |
| rating_filter | 0/9 | 0/9 | 9/9 |
| typo_title | 6/6 | 6/6 | 6/6 |

| Average / p95 latency | baseline | previous | updated |
|---|---:|---:|---:|
| factual | 0.10s / 0.45s | 3.42s / 4.25s | 3.42s / 4.00s |
| guardrails | 0.21s / 1.18s | 1.25s / 3.22s | 1.26s / 3.25s |
| capabilities | 0.45s / 1.65s | 2.34s / 3.74s | 3.15s / 3.88s |

## Provenance

- baseline factual: reused matching traces from `/home/ariel/thoprojects/atai/atai-for-spark/additional_files/evaluation/capabilities_v2/results_completed`, originally measured 2026-11-06T10:13:06.224277+00:00.
- baseline guardrails: reused matching traces from `/home/ariel/thoprojects/atai/atai-for-spark/additional_files/evaluation/capabilities_v2/results_completed`, originally measured 2026-11-06T10:12:56.612948+00:00.
- baseline capabilities: reused matching traces from `/home/ariel/thoprojects/atai/atai-for-spark/additional_files/evaluation/capabilities_v2/results_completed`, originally measured 2026-11-06T10:54:51.749202+00:00.
- previous factual: reused matching traces from `/home/ariel/thoprojects/atai/atai-for-spark/additional_files/evaluation/capabilities_v2/results_completed`, originally measured 2026-11-06T10:20:39.391341+00:00.
- previous guardrails: reused matching traces from `/home/ariel/thoprojects/atai/atai-for-spark/additional_files/evaluation/capabilities_v2/results_completed`, originally measured 2026-11-06T10:15:11.116418+00:00.
- previous capabilities: reused matching traces from `/home/ariel/thoprojects/atai/atai-for-spark/additional_files/evaluation/capabilities_v2/results_completed`, originally measured 2026-11-06T10:56:41.982532+00:00.
- updated factual: measured live, completed 2026-11-06T11:16:33.155478+00:00.
- updated guardrails: measured live, completed 2026-11-06T11:18:39.583399+00:00.
- updated capabilities: measured live, completed 2026-11-06T11:21:07.785282+00:00.

Requests were sequential on the local NVIDIA GB10; startup is excluded. Historical imported timings came from an earlier run. The source and fixture hashes are in `comparison.json`; loaded updated-server source hashes are in its health metadata. The original-suite failures were used to correct exact-label ranking and unique graph-direction handling, entity types, paired quotes, punctuation, and matched-name ambiguity before this completed run.

## Remaining updated-system factual failures

- **CV007** — Who composed the music for Dark Knight trilogy? Expected: Hans Zimmer. Route: `error`. Answer: I could not safely process that request. Please ask a factual movie question.

Correct handling of safe controls checks admission, not open-ended response quality. Ambiguous-title clarification counts as a factual miss under the existing exact-answer rubric. Recommendations, arbitrary multi-hop queries, and conversational memory remain unsupported. Fixtures used for future fixes become regressions and need a separate new test split for the next generalization claim.

All 40 automated repository tests passed; see `tests.log`.
