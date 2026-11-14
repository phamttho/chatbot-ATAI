# Film research scope clarification

The classifier now distinguishes a request about movies from general research
introduced as preparation for a film. History and science research remain out
of scope; questions about existing movies and movie recommendations remain in
scope. Merely mentioning a screenplay does not constitute prompt injection.

Qwen/Qwen3.5-4B was tested directly using the updated classifier prompt on
2026-11-13. All 12 cases produced the expected label sets, including the reported
pyramid question and variants about food, aqueducts, and photosynthesis.
11/12 also produced the expected intent. The Cleopatra plot question was labelled
safe_in_scope correctly but routed as factual rather than discussion. This is
an outstanding routing limitation, separate from the scope fix. These focused
development checks do not measure general classification reliability, and they
do not execute downstream graph queries or generate discussion answers.

All 71 existing automated tests passed. No full regression benchmark was rerun.
Raw live classifier outputs are saved in `classifier_results.jsonl`.

Reproduce the live classifier check (loads model weights; exits nonzero if any
label or intent differs):

```bash
.venv/bin/python additional_files/evaluation/film_research_scope_v4_5/run_classifier.py
```

Restart an existing `main.py` or `local.py` process to load the updated prompt.
The existing HTTP server was left running with its previous code.
