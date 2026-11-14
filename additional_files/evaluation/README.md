# Evaluation

The completed [corrected 3,000-case benchmark](corrected_3k/results_completed_20261106/BENCHMARK.md)
evaluates the current assistant on independently graph-validated factual cases:
2,966/3,000 passes (98.87%), including exact complete answers and correct query
grounding. The [suite instructions](corrected_3k/README.md) explain corrections,
101 graph-only replacement records, provenance and reproduction. The supplied
`more_test_cases.jsonl` remains preserved as the original, flawed input.

The primary evaluation is now the [requirements-based suite](quality/README.md):
96 graph-verified factual cases and 100 guardrail cases. Its [results](quality/RESULTS.md)
include exact answer-set checks and separate refusal/label metrics.

Use `local_eval.py` against a locally running `local.py` server. See the root
README for server and evaluation commands. `run_eval.py` is the preserved
original direct baseline harness; it is not needed for the new HTTP flow.

- `test_cases.jsonl`: original 300 cases, unchanged. Factual answers use keyword
  containment checks and do not prove answer completeness. Some expectations
  reflect real-world facts rather than the supplied graph's altered contents.
- `requirements_cases.jsonl`: 13 explicit examples/regressions, with complete
  answer sets checked against the supplied requirements and graph. Mixed
  guardrail examples require exact label sets. These are development checks,
  not an unseen test set.
- `local_eval.py`: HTTP runner, defaults to a reproducible small sample. Sampling
  groups use `expected_route` when present, otherwise `expected_category` (six
  groups in the original file). `--ids` selects exact cases; `--all` opts into
  the entire selected case file. Both engines use the same runner and cases.
- `results/*.jsonl`: complete per-request outputs, including failed requests.
- `results/*.summary.json`: metrics, case IDs, timestamp, seed, dataset hash.
- `BENCHMARKS.md`: measured results and scoring caveats.

For factual behavior, a graph route is required. Cases with `expected_answers`
compare exact unordered answer sets from the API; original cases check required
terms. Guardrail behavior checks refusal routing, not a semantic safety judge.
The new agent uses fixed refusal text and never executes a graph query for blocked
inputs. Original single-label cases compare the primary label; explicit
`expected_labels` cases require the entire set. Open-ended redirections do not
count as successful discussion. A classification score is independent of an
answer score. Do not interpret these small development runs as a production
safety assessment or as full-dataset accuracy.
