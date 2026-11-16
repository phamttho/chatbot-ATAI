# Mixed movie and out-of-scope requests (v4.7)

When a message contains a separate movie question and an unrelated request, the
classifier now extracts the movie question. The agent answers only that portion
and appends a brief refusal of the unrelated task. Unsafe and prompt-injection
labels still block the entire message. If extraction is missing or invalid, the
agent refuses the full request.

The local evaluation covers 28 reported and targeted questions. It checks exact
classification label sets, graph-backed answers for factual questions, and
guardrail behavior for blocked requests. The recorded Qwen3.5-4B run passed
28/28 cases; see [results.json](results.json). The runner is
[run_cases.py](run_cases.py).

To rerun it, provide the course graph at `additional_files/data/graph.nt` and a
working model runtime, then run:

```bash
python additional_files/evaluation/mixed_scope_v4_7/run_cases.py
```

The runner rewrites `results.json`. Use `--output` to save to another path.
