# Corrected 3,000-case factual benchmark

Completed benchmark: [2,966/3,000 (98.87%)](results_completed_20261106/BENCHMARK.md),
including complete answers and correct executed-query grounding. Mean HTTP
latency was 3.558 seconds; p95 was 4.109 seconds. All 3,000 cases received live
model responses, spanning 1,548 films. See the [failure analysis](results_completed_20261106/FAILURES.md)
for the 34 failures, including nine processing errors.

This is a corrected version of `../more_test_cases.jsonl`. The supplied original
and historical results remain intact. There are exactly 3,000 unique inputs and
entity/relation pairs, with the original 15-relation coverage counts retained.

Construction uses Oxigraph without importing the chatbot or observing model
outputs. `corrections.jsonl` retains every original record and its changes.
`manifest.json` freezes graph, fixture and behavioral source hashes.

Corrections include complete answer sets, 473 numeric distinct-tag-count
answers, explicit film context and paired quotation marks, title/year
disambiguation, 321 derivative-work questions replacing unsupported remake
claims, and 114 distributor questions replacing unsupported platform claims.
101 ambiguous, duplicate or unusable records have deterministic graph-only
replacements for the same relation; these are marked individually. They are
not replacements chosen according to model performance. No records are removed
or substituted after inference.

`validate_gold.py` independently executes every reference query in RDFLib,
verifies complete answer sets and labels, checks film types, and verifies the
intended title/year referent. Decimal lexical spellings such as `8.0` and `8`
are equivalent during independent reference validation. It writes
`gold_validation.json`; the benchmark refuses unvalidated or changed fixtures.

Run against the current assistant on port 8001:

```bash
.venv/bin/python additional_files/evaluation/corrected_3k/validate_gold.py
.venv/bin/python additional_files/evaluation/corrected_3k/run_benchmark.py \
  --url http://127.0.0.1:8001 \
  --output-dir additional_files/evaluation/corrected_3k/my_fresh_run
.venv/bin/python additional_files/evaluation/corrected_3k/audit_query_grounding.py \
  additional_files/evaluation/corrected_3k/my_fresh_run
.venv/bin/python additional_files/evaluation/corrected_3k/analyze_failures.py \
  additional_files/evaluation/corrected_3k/my_fresh_run --grounded
```

The runner preserves per-request results and failures immediately, reports
progress, snapshots the behavioral sources, checks loaded server hashes, and
checks source/fixture hashes again on completion. It sends only natural-language
inputs. All 3,000 cases run live, sequentially, including errors. Choose a fresh
output directory for each run; existing runs cannot be overwritten.

A strict pass requires correct safe factual classification, the exact complete
answer set, correct raw graph values, all answers in the natural-language text,
the project's conjunction requirement, a graph route, and a visible query.
Mean/median/p95 HTTP latency includes classification, planning, graph execution
and response formatting; graph validation and startup are excluded.

The final query audit additionally requires the intended entity, property,
direction and operation in the actual executed query. This audit was added after
inference when two answer-scoring passes were found to use narrative location
instead of filming location, coincidentally returning the same answer. The
frozen answer score (2,968/3,000) is preserved separately; the stronger grounding
score (2,966/3,000) is the headline result. Raw traces and fixtures were unchanged.

The initial server stopped after 290 completed responses. Those responses,
including failures, were reused with full provenance, and cases 291–3,000 ran
after restarting identical sources/model weights. `results_20261106/` is the
interrupted artifact; `results_completed_20261106/` contains all 3,000 completed
responses. The runner now stops on a transport outage and accepts `--reuse-prefix`
to retain completed responses equally, whether they passed or failed.

This is factual coverage across shared templates, not a production distribution
or a guardrail evaluation. Some original inputs appeared in older partial
development runs. Corrections change wording and 101 subjects, so results cannot
be compared directly with the old 63-case partial keyword-scored run.
`construction_draft_before_review/` preserves the pre-inference construction
draft; it was never benchmarked and is not the validated final suite.
