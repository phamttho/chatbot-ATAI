# Stage 3 evaluation

This is a baseline evaluation harness. It does not modify the chatbot logic.

Run a smoke test first:

```bash
python3 additional_files/evaluation/run_eval.py --limit 5
```

Run the complete 300-case evaluation:

```bash
python3 additional_files/evaluation/run_eval.py
```

The runner uses `KNOWLEDGE_GRAPH_PATH` when set; otherwise it uses the graph in
`additional_files/data/graph.nt`. Results are written to `additional_files/evaluation/results/`:

For Qwen evaluation, set `QWEN_MODEL_PATH` to a complete local
`Qwen2.5-1.5B-Instruct` directory. The directory must contain `config.json`,
`tokenizer.json`, and model weights (`*.safetensors` or `*.bin`). If the variable
is not set, Transformers loads `Qwen/Qwen2.5-1.5B-Instruct` from its Hugging Face
cache or attempts a download.

For Nuvolos, use the local Transformers model. The original
`MOVIE_LLM_MODEL` environment variable remains supported; otherwise the
default is `Qwen/Qwen2.5-1.5B-Instruct`. No API token is required.

Live message handling defaults to a 5-second deadline. Override it with
`MESSAGE_TIMEOUT_SECONDS` only when testing slower hardware.

To download it into this project when network access is available:

```bash
python3 additional_files/scripts/download_qwen.py
export QWEN_MODEL_PATH="$PWD/additional_files/models/Qwen2.5-1.5B-Instruct"
```

- `latest_results.json`: one record per test case, including response, latency, route, and pass/fail.
- `latest_summary.json`: overall pass rate, classification accuracy, per-category precision/recall/F1,
  latency, and a confusion matrix.

The 300 cases contain 70 factual movie questions, 55 open-ended movie questions, 60 out-of-scope questions, 55 toxic messages, and 60 unsafe requests. The factual answer checks are intentionally
conservative keyword checks; failures should be manually reviewed before changing the chatbot.
