# Numeric movie counts and ten-item comma-separated display

The user requested at most ten names separated by commas, and a number for
`How many movies did Christopher Nolan direct?`.

The application now enforces an explicit `How many movies/films` request before
query execution. If Qwen proposes a list or an inverse lookup, it is converted
to a validated movie selection with `result: count`. Filters and the retrieved
person are preserved. The backend executes `COUNT(DISTINCT ?answer)` over film
records, not the displayed list. Raw model output and any original plan remain
in the response alongside a recorded plan adjustment. Ordinary tag counts and
phrases inside quoted titles are not interpreted as movie-count requests.

Both HTTP answer text and Speakeasy replies show at most ten comma-separated
values. Titles containing commas or quotation marks are CSV-quoted. Complete
`answers` and RDF `values` remain available in metadata; `displayed_answers`
identifies the shown subset. Large lists include an explicit showing-ten note,
and earliest/latest ties are acknowledged. Numeric count answers stay numeric.

Independent validation found **11 movie records directed by Christopher Nolan**
and **27 directed by Martin Scorsese** in the supplied altered graph. Counts
require a recorded film type; a trilogy/collection is not counted as a movie.
Oxigraph reference SPARQL counts were independently checked by RDFLib traversal
over all relevant P31/P57/label triples. Display cases retain previously verified
gold with an unchanged graph hash. All ten cases were frozen before inference.

Completed checks:

| Check | Passed | Meaning |
|---|---:|---|
| Automated tests | 66/66 | Includes forced wrong-model-plan correction, no tag/title false matches, ten-item limit and CSV quoting |
| Focused live requests | 10/10 | Real Qwen; numbered/plain Nolan counts, another director, earliest/latest lists, year count, tags, composer and screenwriters |
| Offline display replay | 243/243 | Previously saved v4.1 model/graph responses passed through the new formatter; **no new model inference** |

The initial offline replay flagged CV042 because its title contains a quotation
mark, which CSV represents by doubling it. CSV parsing confirmed the displayed
title was correct. The evaluator now decodes that escape; the correction has a
unit test. The initial 242/243 replay result remains preserved in
`results/summary.json`, and the corrected replay is recorded separately in
`format_replay_final.json`. Application source, gold and model outputs did not
change during that evaluator correction. The user-requested comma/ten-item
policy replaces the older “and”/full-text display rule; exact complete graph
answer sets are still checked in metadata.

Evidence: `cases.jsonl`, `manifest.json`, `validation.log`, `unit_tests_final.log`,
`results/live.jsonl`, `results/provenance.json`, and `format_replay_final.json`.
Only natural-language input was sent for the ten live requests. No Speakeasy
login or room messages were sent by the checks. These are focused regressions,
not a new 243-case live benchmark or a rerun of the historical 3,000 cases.

Restart the existing Speakeasy bot to load the new code: Ctrl+C, then
`python main.py`. Its configured credentials are retained.
The local API on port 8001 was refreshed and its loaded source hashes match the
tested revision (`local_server_8001_health.json`). The temporary validation
server on port 8002 was stopped after checks.

For a fresh focused run against a current local server, use `run_cases.py` with
`--manifest reproduction_manifest.json` (use its full project-relative path) and
a fresh `--output-dir`. This manifest changes only the evaluator hash after CSV
decoding was corrected; the original manifest and runner are preserved in the
original artifacts, including `results/runner_original.py`.
