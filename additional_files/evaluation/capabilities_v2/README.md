# Capability extension and comparison

This extension adds support and evaluation for shortened titles, quoted
misspellings, user tags/ratings, distinct counts, and numeric filters. The graph
is the sole factual reference. `manifest.json` freezes 47 fixtures before model
inference: three supplied user regressions and 44 additional graph-derived cases
selected with seed 20261108. The fixtures share templates and are a coverage
suite, not a random sample of production traffic or an independently annotated
safety assessment. Existing quality cases are retained without changing gold.

`build_suite.py` uses Oxigraph and never imports a chatbot. The runner independently
validates every new complete answer set and entity alias using RDFLib, then
sends only each natural-language question to the servers. Counting is over
distinct values. Rating filters require a recorded rating; “not below” means
`>=`, and “not above” means `<=`. Missing ratings do not qualify.

Run the current code in one terminal:

```bash
.venv/bin/python local.py --engine llm --model Qwen/Qwen3.5-4B --port 8001
```

In another terminal, evaluate the updated system on 96 original factual cases,
100 guardrail cases, and 47 new capability cases:

```bash
.venv/bin/python additional_files/evaluation/capabilities_v2/run_evaluation.py \
  --systems updated --updated-url http://127.0.0.1:8001 \
  --output-dir "additional_files/evaluation/capabilities_v2/results_$(date +%Y%m%d_%H%M%S)"
```

For a full three-system comparison, start the legacy baseline on port 8000,
the previous 4B code on port 8001, and the updated code on port 8002. The
`prechange_sources` directory preserves the previous graph store, agent, and
transport. The model runtime was not changed. To start that previous code:

```bash
PYTHONPATH="additional_files/evaluation/capabilities_v2/prechange_sources:additional_files/src/chatbot:additional_files/evaluation" \
  .venv/bin/python -c 'from local_api import main; main()' \
  --engine llm --model Qwen/Qwen3.5-4B \
  --graph additional_files/data/graph.nt --port 8001
```

Then run:

```bash
.venv/bin/python additional_files/evaluation/capabilities_v2/run_evaluation.py \
  --output-dir "additional_files/evaluation/capabilities_v2/results_$(date +%Y%m%d_%H%M%S)"
```

`--reuse-quality PATH` explicitly reuses matching original-suite baseline and
previous-version traces from that directory; their timestamps and import source
remain in summaries. The updated system and new capability cases always run
live. Without that option, every selected system runs every case live. Requests
are sequential; model requests do not overlap.

Each run preserves flushed response JSONL, summaries, independent gold
validation, hashes of the on-disk agent sources, and a `comparison.json`.
The updated server additionally reports hashes captured when it initialized,
so its loaded code can be compared with disk. Historical servers do not expose
those startup hashes. Original frozen results are retained in `../quality`.
The old `quality/run_comparison.py` requires the historical source hashes and
intentionally does not accept the updated agent.

Earlier interrupted runs are retained in `results_initial`,
`results_regression_debug`, `results_completed`, `results_verified`, and
`results_release`. They contain debugging or startup checks, not the final
comparison. Original-suite checks exposed exact-label/article ranking,
graph-direction, film-versus-other-work, apostrophe/punctuation, and role-word
retrieval regressions. Those existing cases were used to debug the implementation.

Use `results_final_verified` for the final comparison. Its baseline and previous
measurements are explicitly imported from the completed portions of earlier
runs; the updated system is evaluated live on all 243 cases. The additional
capability fixtures were unchanged, and no updated-system capability outputs
were used to tune the implementation before the final run.

`--reuse-results PATH` reuses matching completed baseline/previous suites from a
capability run. The updated system always runs live. Both reuse modes verify
case identity and hashes and retain measurement timestamps and import paths.
The runner waits for server readiness before timing requests.

To write a report from a completed comparison:

```bash
.venv/bin/python additional_files/evaluation/capabilities_v2/summarize_results.py \
  additional_files/evaluation/capabilities_v2/results_final_verified
```

Final measurements and remaining failures: [verified results](results_final_verified/RESULTS.md).
