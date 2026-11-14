# LLM movie recommendations

Safe recommendation and movie-discussion requests now call Qwen directly after
classification. The old factual-question redirection was removed. A request for
one movie gets one title and a short reason. Requests with any blocked label
still return fixed conversation stoppers before recommendation generation.
Factual questions continue through the validated graph planner and count/display
rules. Generated recommendations carry `route: movie_discussion` and
`answer_source: language_model`, with no purported graph query or graph answers.

All 69 automated tests passed (`unit_tests.log`). The three added tests verify
LLM recommendation generation without graph access, blocked mixed requests
stopping before generation, and empty generations failing without invented data.

Only six focused live checks were run, as requested; all six passed:

| Request | Observed result |
|---|---|
| 1. Recommend a science-fiction movie. | Arrival, with a short description |
| Recommend a crime movie. | The Godfather, with a short description |
| Crime movie plus real-world crime instructions | unsafe refusal; one classifier call |
| Crime novel plus real-world crime instructions | unsafe + out_of_scope refusal; one classifier call |
| How many movies did Christopher Nolan direct? | 11 |
| First film released after 2002? | Ten comma-separated titles and the 94-tie note |

The first two requests each used two actual Qwen calls: classification, then
natural-language generation. Subjective recommendation quality has no exact-title
gold; the observed titles/descriptions were manually inspected for the requested
genres. Counts and tie expectations reuse independently verified graph results.
Fixtures were reviewed and frozen before inference. Request/response traces,
call counts, routes, source hashes and results are in `results/`; model outputs
are preserved verbatim. No Speakeasy login or room messages were sent by testing.
No 243/300/3,000-case benchmark was rerun for this change.

The local API on port 8001 is running the tested v4.3 sources. Restart the user's
existing Speakeasy process (Ctrl+C, then `python main.py`) to load this code;
the running Speakeasy process was not restarted automatically.
