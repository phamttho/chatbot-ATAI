# Prompt clarification regression results

The unchanged Qwen 3.5 4B model was evaluated live on all 243 existing cases.
The expected answers, reference queries, fixtures, and scorer were unchanged.
This suite has now been used for debugging and measures regression coverage,
not accuracy on unseen production questions.

| Suite | Earlier verified run | Prompt clarification |
|---|---:|---:|
| Original factual | 96/96 | 96/96 |
| Guardrails (exact labels and handling) | 90/100 | 100/100 |
| Capability extension | 46/47 | 46/47 |
| Total | 232/243 (95.5%) | 242/243 (99.6%) |

The classifier prompt distinguishes an instruction override from a separate
unrelated task and asks it to classify each action in mixed requests. All ten
previous guardrail failures now pass. All ten requests were already correctly
refused in the earlier run; most improvements concern exact classification.

The planner prompt prioritizes the full matching name over the individual-film
flag for series and collections. The previous Dark Knight trilogy failure now
passes, returning Hans Zimmer from the graph.

## Remaining failure

CV034: What is the user rating of "Death Machines Vol. 2"?
The model emitted Q64221165549070 instead of the retrieved Q6422116554907003.
Validation rejected the invented/truncated ID and returned an error, rather
than accepting an ungrounded answer. The graph reference rating is
3.182346089731368. This case passed in the earlier run; the new prompts therefore
fix eleven prior failures but introduce one observed regression.

## Additional checks and provenance

All 40 automated repository tests passed (tests.log).
Twelve new manually authored guardrail boundary checks were frozen before their
first inference and evaluated after the main run: 12/12 passed. They cover
standalone injection, independent unrelated tasks, three-label mixed requests,
and safe fictional discussion. They have no independent human review and are
reported separately, not added to the 243-case score. No further prompt tuning
was performed after either run. See new_boundary_checks/ for traces and hashes.

The standard server on port 8001 was restarted with the evaluated sources.
Its health source hashes match the evaluation server on port 8002 and the saved
source_snapshot/. See promoted_server_health.json and comparison.json.
The capability gold answers were independently checked with RDFLib before
inference. All request and response traces, scores, source hashes and fixture
hashes are preserved in this directory. Earlier results remain unchanged.
