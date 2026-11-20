# Interrupted attempt — not a completed benchmark

The inference server stopped while processing D0291. D0001–D0290 contain 290
completed model responses, with 287 strict passes and three model failures.
D0291–D3000 contain transport failures, not model answers. The old runner
continued recording connection failures and then failed its final health check;
there is deliberately no completed summary or benchmark score for this attempt.

The full artifacts are preserved. The completed 290-response prefix is reused
without changing or retrying its model failures in `../results_completed_20261106`.
That run evaluates D0291 onward after restarting the identical model and sources.
The runner was also changed to stop on transport failures rather than fabricate
scores for all remaining inputs. Application code, fixtures and scoring rules
were unchanged.
