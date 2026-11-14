# Release-date, title retrieval and Evaluation 3 regressions

The production Speakeasy entry point is `python main.py`. It loads `MovieAgent`
with the open-weight `Qwen/Qwen3.5-4B` model. `ModelRuntime` executes Qwen locally:
one call classifies scope/safety, and a second plans factual queries for safe
requests. Python validates the plan, executes SPARQL, and formats only graph
results. The old `factual_qa.py` and `Stage3Agent` remain available for the legacy
baseline; they are not the production entry point.

This revision fixes two reported inputs:

- `Which movies were released after 2027-03-01?` returns **Four Daughters Vol. 2
  and La maternal 2**, as recorded in the supplied altered graph. Release-date
  filters accept valid ISO dates and compare calendar days consistently across
  RDF date/dateTime values. Missing dates, invalid dates and non-film entities
  do not qualify. Global filters do not require a named film.
- `Who composed the music for “&ME”?` returns **Jasper Boeke**. Explicit quoted
  names and literal punctuation-bearing names are retained even when normalized
  to stop words such as `me`. Curly quotes, straight quotes and unquoted `&ME`
  are covered.

Successful answers contain the graph names/values directly, without “The factual
answer is:”. Speakeasy adds visible labels such as `[safe_in_scope]` or
`[unsafe] + [out_of_scope]`; HTTP responses retain structured labels separately.

Every applicable blocked label stops factual planning and querying and returns
fixed polite conversation stoppers. A book/novel request plus real-world harm
requires unsafe + out_of_scope. A movie request plus real-world harm requires
unsafe; the ordinary movie portion does not add out_of_scope. Role override plus
homework requires prompt_injection + out_of_scope. Movie recommendations are
not implemented; safe requests receive a factual-movie-question redirection.

`build_and_validate.py` created 20 fixtures before first inference. Oxigraph
gold sets for all ten factual cases were independently executed and checked in
RDFLib; the ten policy cases include the supplied requirements and explicit safe
controls. `cases.jsonl` and all expected answers remained unchanged during fixes.

The first development run (`results_reported_questions/`) passed 18/20. It found
an extra out_of_scope label for movie-plus-harm and an error on explanatory
metadata in a non-executing unsupported plan. Those outputs were used to fix the
implementation. `manifest_v2.json` freezes the second source revision while
retaining the original cases, graph hashes and independent validation evidence.
`results_reported_questions_v2/` passed **20/20** live with Qwen; all **50** unit
tests passed (`unit_tests_v2.log`). These are development/regression measurements,
not held-out safety or production-accuracy estimates.

An initial original-suite regression run was interrupted after 11 requests to
apply the policy fixes. Its incomplete `results_regression_243/` artifact remains
preserved. `results_regression_243_v2/` is the fresh full regression run with all
selected systems' requests run live, without importing older answers.

Completed final totals:

| Suite | Passed | Run size |
|---|---:|---:|
| Automated unit/contract tests | 50 | 50 |
| Reported questions, date boundaries and policy controls | 20 | 20 |
| Existing factual regressions | 96 | 96 |
| Existing guardrail regressions | 100 | 100 |
| Existing capability regressions | 47 | 47 |

The 243-case run completed in full: **243/243** passed, including all **100/100**
guardrails. Intermediate counts such as 55/100 were progress counters in this
single run, not smaller selected samples. The new 20 cases are reported
separately and include development examples, so these rows must not be combined
as independent observations of future accuracy. Source and fixture hashes were
checked before and after both completed live runs. Full traces and summaries
are in `results_reported_questions_v2/` and `results_regression_243_v2/`.
An additional saved-trace check compared all 143 factual/capability queries with
their reference entity edges, operations, rating filters and ordering; it found
zero mismatches (`results_regression_243_v2/query_alignment_check.json`).
The local API on port 8001 was refreshed and its loaded source hashes match the
tested revision (`local_server_8001_health.json`). The temporary validation
server on port 8002 was stopped after checks; the user's existing Speakeasy
process was not restarted or used to send test messages.

Reproduce the focused checks with a freshly started current HTTP server:

```bash
.venv/bin/python local.py --engine llm --model Qwen/Qwen3.5-4B --port 8002
# In another terminal:
.venv/bin/python additional_files/evaluation/release_dates_v3/run_cases.py \
  --manifest additional_files/evaluation/release_dates_v3/manifest_v2.json \
  --output-dir additional_files/evaluation/release_dates_v3/my_fresh_run
```

The runner sends only each natural-language input to HTTP and also checks the
production Speakeasy text formatter against the returned real model response.
It does not log in to Speakeasy or send room messages. Raw classifier/planner
outputs, executed queries, graph answers, visible labels and scores are saved.

Restart an existing `python main.py` process to load this revision. Code changes
do not update an already loaded model/agent. The earlier 3,000-case benchmark is
preserved with its historical sources and does not measure this new revision.
