# Corrected 3,000-case benchmark

Model: Qwen/Qwen3.5-4B (cuda); all 3,000 requests ran live, sequentially through HTTP.

Strict passes: **2968/3000 (98.93%)**.
Classification accuracy: 100.00%. API/model processing errors: 9.
Mean / median / p95 latency: 3.558s / 3.521s / 4.109s.
Measured request time: 177.88 minutes. Startup and independent data validation excluded.

| Relation | Passed | Total | Pass rate |
|---|---:|---:|---:|
| cast | 20 | 20 | 100.00% |
| cinematographer | 61 | 62 | 98.39% |
| composer | 55 | 57 | 96.49% |
| count_tags | 472 | 473 | 99.79% |
| derivative_work | 305 | 321 | 95.02% |
| director | 4 | 5 | 80.00% |
| distributor | 114 | 114 | 100.00% |
| editor | 223 | 223 | 100.00% |
| filming_location | 473 | 478 | 98.95% |
| narrative_location | 247 | 247 | 100.00% |
| original_language | 6 | 6 | 100.00% |
| producer | 50 | 50 | 100.00% |
| production_company | 435 | 438 | 99.32% |
| screenwriter | 26 | 27 | 96.30% |
| user_rating | 477 | 479 | 99.58% |

The initial server stopped after 290 completed responses. Those responses, including model failures, were preserved from /home/ariel/thoprojects/atai/atai-for-spark/additional_files/evaluation/corrected_3k/results_20261106. The remaining cases ran after restarting the identical model/source revision. Connection failures in the interrupted artifact are infrastructure failures and were not treated as model answers. No completed model answer was retried. Startup and downtime are excluded from request latency.

A pass requires safe factual classification, a graph-answer route, the exact complete answer set (no missing or extra values), matching raw RDF values, every answer in the response text, the required conjunction for multiple answers, and a visible query. Failures are retained and never replaced after inference.

The supplied dataset was corrected before inference: all tag-count gold answers were recalculated, complete graph answer sets replaced keywords, title/year context was resolved, remake wording became derivative work, and distribution-platform wording became distributor. Of 3,000 records, 101 unresolved/duplicate/unusable records were replaced deterministically from the graph with the same relation. All replacements and original records are recorded in ../corrections.jsonl. All 3,000 intended entities and reference queries passed independent RDFLib validation before the first request.

This is a graph-grounded factual coverage benchmark with 15 shared templates and uneven relation counts. It does not measure guardrails or establish production accuracy. Some original records had been used in earlier partial development evaluation; this is not a pristine held-out dataset. The source and prompts were unchanged throughout this run.

See summary.json, responses.jsonl, failures.jsonl, provenance.json, and source_snapshot/ for complete evidence.
