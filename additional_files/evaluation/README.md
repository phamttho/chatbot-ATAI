# Evaluation

The retained [Qwen 3.5 4B benchmark report](BENCHMARK.md) records the completed
3,000-case factual evaluation: 2,966/3,000 cases (98.87%) passed complete-answer
and executed-query grounding checks. This result used a saved earlier source
revision; see the report for methodology and limitations.

For a small local HTTP evaluation, run `local_eval.py` against a running
`local.py` server. It uses `test_cases.jsonl` by default. Pass
`requirements_cases.jsonl` with `--cases` for the 13-case requirements sample.
These small checks are development measurements, not a held-out accuracy estimate.
