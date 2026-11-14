# Corrected 3,000-case benchmark

**2966/3000 passed (98.87%)** with correct complete answers and reference query grounding.

Model: Qwen/Qwen3.5-4B, revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a, on NVIDIA GB10 (CUDA). All 3,000 cases were evaluated live through HTTP.

| Metric | Result |
|---|---:|
| Fully correct answers and query grounding | 2966/3000 (98.87%) |
| Failures, including processing errors | 34 |
| Processing errors | 9 |
| Frozen complete-answer score before query audit | 2968/3000 (98.93%) |
| Mean HTTP latency | 3.558s |
| Median HTTP latency | 3.521s |
| p95 HTTP latency | 4.109s |
| Total measured request time | 177.88 min |

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
| filming_location | 471 | 478 | 98.54% |
| narrative_location | 247 | 247 | 100.00% |
| original_language | 6 | 6 | 100.00% |
| producer | 50 | 50 | 100.00% |
| production_company | 435 | 438 | 99.32% |
| screenwriter | 26 | 27 | 96.30% |
| user_rating | 477 | 479 | 99.58% |

The original 3,000 cases were corrected before inference, including complete answer sets, distinct tag counts, title/year references, and graph-accurate derivative-work/distributor wording. 101 ambiguous, duplicate or unusable records were replaced deterministically with the same relation; 2,899 original subjects were retained. Every reference query and intended film entity passed independent RDFLib validation before inference. The original data and all changes are preserved in ../corrections.jsonl.

A pass requires safe factual classification, a graph route and visible query, the exact complete answer set and raw RDF values, all answers in the response text, the required conjunction for multi-answer responses, and the correct reference entity, relation, direction and operation. No model outputs were used to alter the cases, gold answers, prompts or application code.

The frozen answer scorer initially counted 2968 passes. A final audit of all 3,000 executed-query traces additionally rejected 2 coincidentally correct answer sets obtained from a different graph relation. The frozen score is preserved in summary.json and RESULTS.md; the stronger grounding result is recorded separately in grounded_summary.json and grounding_audit.json. This query audit was added after inference and is explicitly reported as a scoring correction, not an independently preregistered metric.

Cases added to the failure list by the query audit:

- D2356: Where was the film "Author! Author!" filmed? Expected P915; observed {'operation': 'lookup', 'entity': 'Q646972', 'property': 'P840', 'direction': 'outgoing'}. Identical answer text does not make the wrong relation correct.
- D2510: Where was the film "Bad Boys" released in 1983 filmed? Expected P915; observed {'operation': 'lookup', 'entity': 'Q798650', 'property': 'P840', 'direction': 'outgoing'}. Identical answer text does not make the wrong relation correct.

The initial server stopped after 290 completed responses. Those responses, including failures, were preserved; the remaining 2,710 cases ran after restarting the identical model and sources. Infrastructure connection failures remain in the interrupted artifact and were not treated as model responses. No completed model answer was retried. Startup and downtime are excluded from latency. Behavioral sources and fixtures passed the final unchanged-hash checks.

This is a factual coverage suite with 15 shared templates and uneven relation counts, not a production accuracy estimate or guardrail benchmark. Some original records appeared in earlier partial development evaluations. The corrected/replacement cases were frozen before this full run.

Evidence: responses.jsonl, grounded_failures.jsonl, grounded_summary.json, grounding_audit.json, provenance.json, source_snapshot/, and ../gold_validation.json.
