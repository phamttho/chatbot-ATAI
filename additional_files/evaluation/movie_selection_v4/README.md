# Composable movie selection: reported-query regressions

This revision adds a structured movie selection to the Qwen planner. The plan
separates `filters` from the requested `result`: `list`, `count`, `earliest`, or
`latest`. Python validates those fields and constructs bounded graph queries.
Date filters, person/relation conditions and ratings can be combined before
counting or finding an extreme. Existing single-entity lookups remain supported.

Semantics:

- `in 2010` covers the entire calendar year. `after 2002` excludes the entire
  year 2002; `before 1990` excludes 1990. Full ISO-date comparisons remain
  available. RDF dates and dateTimes compare by recorded calendar day.
- Counts use `COUNT(DISTINCT ?answer)` over movie entities, so multiple release
  dates and multiple recorded film types do not duplicate the count.
- Earliest/latest operates on matching recorded release dates and returns all
  tied movies. Ordering alone introduces no unrequested date cutoff.
- A negated director condition requires a recorded director and uses
  `FILTER NOT EXISTS` for the excluded person. Co-directed films containing that
  person are excluded. Missing director data is not treated as proof of a
  different director.
- Unlabelled entities remain real graph records. They are included in counts
  and explicitly displayed as `Unlabelled graph entity (Q...)` rather than
  dropped, given an invented name, or allowed to crash a broad query.
- HTTP results retain all matching names and IDs. Speakeasy displays an
  explicitly labelled 25-title preview plus the total for large results,
  including large tied extrema. This keeps room messages readable and makes
  partial display explicit. Additional conditions narrow the result.
- Separate pasted questions prompt a request to send them separately. A single
  question combining conditions (for example, a year and a director exclusion)
  is compiled as an intersection.

The 20 cases in `cases.jsonl` include the pasted questions verbatim, their
numbered/unnumbered versions, different years, zero counts, empty extrema,
combined conditions, the previous `&ME` question, and two pasted-question checks.
Expected answer sets were constructed with Oxigraph reference SPARQL and
independently checked with RDFLib traversal and Python calendar comparisons
before model inference. Validation preserved unlabelled records. The independent
reference uses `YEAR(...)` for year questions rather than copying the production
compiler's date-range expansion.

Graph-derived expected results include:

| Question | Expected result |
|---|---|
| How many movies were released in 2010? | 217 |
| First film released after 2002? | 94 tied movie records |
| Latest movie released before 1990? | Voyage to Melonia and The Wizard |
| Movies released before 1990? | 6,011 movie records |
| Films not directed by Christopher Nolan? | 13,034 movie records with a recorded director |
| Count before 1990, excluding Nolan? | 6,002 |
| How many films came out in 2011? | 241 |
| How many films were released in 1800? | 0 |

These are facts from the supplied altered graph, not a real-world film census.
Shared templates, authored cases and regression-driven fixes do not establish
accuracy on unseen movie questions.

`results_reported/` passed 20/20 before the first broader regression check. That
initial `results_regression_243/` run exposed unrequested date filters on some
earliest-film-by-director questions and was interrupted. The planner instruction
was corrected to distinguish ordering from a date cutoff. Cases and gold answers
were unchanged. `run_manifest_v2.json` records the resulting source revision.
`results_reported_v2/` passed all **20/20** cases with real Qwen inference,
including complete raw RDF answer sets and equivalent-filter semantics.

The full 243-case regression is recorded separately in
`results_regression_243_v2/`. It runs every selected case live without importing
older answers. The automated contract suite contains 60 tests, including tiny
independent graph fixtures for year boundaries, counts, multiple dates/types,
co-directors, unknown directors, ties, unlabelled records and query injection.

Completed final results for v4.1:

| Suite | Passed | Total |
|---|---:|---:|
| Automated unit/contract tests | 60 | 60 |
| Pasted questions and authored variants | 20 | 20 |
| Existing factual regressions | 96 | 96 |
| Existing guardrails | 100 | 100 |
| Existing capability regressions | 47 | 47 |

The full existing live regression run passed **243/243**. Both live runs verified
source and fixture hashes before and after inference. All results, including
full large answer sets and the actual Speakeasy previews, are preserved in
`results_reported_v2/responses.jsonl`; regression traces and summaries are in
`results_regression_243_v2/`. Unit-test output is in `unit_tests_v2.log`.
An additional saved-trace audit checked raw RDF answer values and intended query
entities, relations, result types, ordering and filters for all 143 factual and
capability cases, finding zero mismatches (`query_alignment_check.json` in the
regression directory). The local API on port 8001 was refreshed and its loaded
v4.1 hashes match the tested revision (`local_server_8001_health.json`). The
temporary validation server on port 8002 was stopped. The user's active
Speakeasy process was left running and must be restarted to load these changes.

To reproduce the 20 focused cases with the current source revision:

```bash
.venv/bin/python local.py --engine llm --model Qwen/Qwen3.5-4B --port 8002
# In another terminal:
.venv/bin/python additional_files/evaluation/movie_selection_v4/run_cases.py \
  --manifest additional_files/evaluation/movie_selection_v4/run_manifest_v2.json \
  --output-dir additional_files/evaluation/movie_selection_v4/my_fresh_run
```

Only each natural-language question is posted to the local HTTP API. No gold
answers, reference queries or intended plan fields are sent to Qwen. The runner
also applies the production Speakeasy formatter to the returned real response;
it does not log in to Speakeasy or send room messages. The 3,000-case historical
benchmark belongs to an earlier source version and has not been rerun here.

Restart an existing `python main.py` process to load the new code. Its existing
configured credentials are retained.
