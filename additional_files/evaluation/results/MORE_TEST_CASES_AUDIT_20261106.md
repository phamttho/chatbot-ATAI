# Audit of the supplied 3,000 cases

All 3,000 records in `../more_test_cases.jsonl` were inspected before any new
model evaluation. `../audit_more_test_cases.py` loads the supplied graph with
RDFLib and checks question templates, exact title labels, requested relations,
expected terms and duplicate inputs. It does not import or call the chatbot.
Per-case evidence and input hashes are in `more_test_cases_full_audit_20261106.json`.
The original dataset and historical results were preserved.

The file is unsuitable for a trustworthy headline accuracy score as supplied:

- All 473 tag-count questions expect nonnumeric tag text, not counts. For
  example D2997 asks how many tags At Close Range has but expects “murder”.
- 169 records have no exact title label in the graph. They need alias/year
  resolution and review; this check alone does not prove they are incorrect.
- 778 records match multiple exact title entities. They need entity/type
  disambiguation; duplicate labels alone do not prove the question is ambiguous.
- 321 remake questions need semantic review: the checked graph relation P4969
  means derivative work, which does not by itself establish a remake.
- 114 distribution-platform questions need semantic review: P750 means
  distributor, which does not by itself establish a viewing platform.
- D0848 and D0855 contain the same Anna Christie (1930) rating question.
- All 3,000 records are safe factual requests, spread across just 15 templates.
  They do not measure guardrails or broad paraphrase generalisation.
- Expected keyword containment cannot prove complete answer sets or reject
  additional incorrect answers.

1,452 records have at least one audit flag. Counts overlap. Flags include cases
needing review, not just proven wrong answers. For non-count questions with an
exact title match, this audit found the expected terms under the mapped relation
for at least one matching entity. That is weaker than validating the intended
entity and complete answer set. The remaining unflagged cases are not certified
gold fixtures or independently human-reviewed.

Historical evidence: `larger_qwen4_factual.jsonl` contains 63 recorded requests
from this file (38 keyword-scored passes), without a completed summary. The
separate 90-case guardrail run used a different file. There is no saved completed
3,000-case run in the inspected evaluation artifacts. These partial results also
predate the current implementation.

Before a full model run, resolve each title to a reviewed graph entity, correct
count gold using COUNT(DISTINCT), settle remake/platform semantics, deduplicate,
and freeze complete answer sets and reference queries. Independently validate
those references before inference. Preserve this supplied file as historical
input and report any corrected suite under its own identity.
