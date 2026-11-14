"""Audit every saved executed query against its intended entity/relation/operation.

This post-run audit strengthens the frozen answer scorer: coincidentally equal
answers from the wrong relation are failures. Original scores remain preserved.
No model is called, and no questions, reference answers, or application code change.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from build_suite import HERE, digest

sys.path.insert(0, str(HERE.parent / 'quality'))
from run_suite import summarize


def matches_reference(case, response):
    query = response.get('query') or ''
    edge = re.search(r'WHERE\s*\{\s*(wd:Q\d+|\?\w+)\s+(wdt:P\d+|atai:(?:tag|rating))\s+(wd:Q\d+|\?\w+)\s*\.', query)
    if not edge:
        return False
    expected_entity = 'wd:' + case['entity'].rsplit('/', 1)[-1]
    return (edge[1] == expected_entity and edge[2].split(':')[1] == case['property']
            and edge[3].startswith('?')
            and bool(re.search(r'COUNT\s*\(', query)) == (case['direction'] == 'count'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    args = parser.parse_args()
    out = args.results
    original = json.loads((out / 'summary.json').read_text())
    rows = [json.loads(line) for line in (out / 'responses.jsonl').read_text().splitlines()]
    cases = [json.loads(line) for line in (HERE / 'factual.jsonl').read_text().splitlines()]
    assert len(rows) == len(cases) == original['n'] == 3000
    assert [row['case'] for row in rows] == cases
    source_hash = digest(out / 'responses.jsonl')
    scores, corrected, additional = [], [], []
    for row in rows:
        grounded = matches_reference(row['case'], row['response'])
        passed = bool(row['scores']['passed'] and grounded)
        scores.append(dict(id=row['case']['id'], frozen_answer_passed=row['scores']['passed'],
                           reference_query_grounding=grounded, passed=passed))
        corrected.append(dict(row, scores=dict(row['scores'], passed=passed,
                                              reference_query_grounding=grounded)))
        if row['scores']['passed'] and not grounded:
            additional.append(dict(id=row['case']['id'], input=row['case']['input'],
                                   expected_property=row['case']['property'],
                                   observed_plan=row['response'].get('query_plan'),
                                   expected_answers=[a['label'] for a in row['case']['gold_answers']],
                                   observed_answers=row['response'].get('answers')))
    summary = dict(timestamp=datetime.now(timezone.utc).isoformat(), server=original['server'],
                   suite_sha256=original['suite_sha256'], **summarize(corrected, 'factual'),
                   frozen_answer_passed=original['passed'], frozen_answer_pass_rate=original['pass_rate'],
                   additional_grounding_failures=additional,
                   total_request_seconds=original['total_request_seconds'],
                   imported_prefix_count=original['imported_prefix_count'],
                   provenance=dict(audit_script_sha256=digest(Path(__file__)),
                                   responses_sha256=source_hash,
                                   note='Post-inference audit of every executed query against its reference entity, relation and operation; frozen answer scores and raw traces are unchanged.'))
    replacements = {c['id'] for c in map(json.loads, (HERE / 'corrections.jsonl').read_text().splitlines()) if c['replacement']}
    summary['correction_subsets'] = {name: dict(n=len(subset), passed=sum(r['scores']['passed'] for r in subset))
        for name, subset in [('retained_subjects', [r for r in corrected if r['case']['id'] not in replacements]),
                             ('replaced_records', [r for r in corrected if r['case']['id'] in replacements])]}
    (out / 'grounding_audit.json').write_text(json.dumps(dict(summary=summary, scores=scores), ensure_ascii=False, indent=2) + '\n')
    (out / 'grounded_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    with (out / 'grounded_failures.jsonl').open('w') as stream:
        for row in corrected:
            if not row['scores']['passed']:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    lines = ['# Corrected 3,000-case benchmark', '',
             f"**{summary['passed']}/3000 passed ({100*summary['pass_rate']:.2f}%)** with correct complete answers and reference query grounding.", '',
             f"Model: {original['server']['model']}, revision {original['server']['revision']}, on NVIDIA GB10 (CUDA). All 3,000 cases were evaluated live through HTTP.", '',
             '| Metric | Result |', '|---|---:|',
             f"| Fully correct answers and query grounding | {summary['passed']}/3000 ({100*summary['pass_rate']:.2f}%) |",
             f"| Failures, including processing errors | {3000-summary['passed']} |",
             f"| Processing errors | {summary['errors']} |",
             f"| Frozen complete-answer score before query audit | {original['passed']}/3000 ({100*original['pass_rate']:.2f}%) |",
             f"| Mean HTTP latency | {summary['latency_ms']['mean']/1000:.3f}s |",
             f"| Median HTTP latency | {summary['latency_ms']['median']/1000:.3f}s |",
             f"| p95 HTTP latency | {summary['latency_ms']['p95']/1000:.3f}s |",
             f"| Total measured request time | {original['total_request_seconds']/60:.2f} min |", '',
             '| Relation | Passed | Total | Pass rate |', '|---|---:|---:|---:|']
    for name, group in summary['groups'].items():
        lines.append(f"| {name} | {group['passed']} | {group['n']} | {100*group['pass_rate']:.2f}% |")
    lines += ['', 'The original 3,000 cases were corrected before inference, including complete answer sets, distinct tag counts, title/year references, and graph-accurate derivative-work/distributor wording. 101 ambiguous, duplicate or unusable records were replaced deterministically with the same relation; 2,899 original subjects were retained. Every reference query and intended film entity passed independent RDFLib validation before inference. The original data and all changes are preserved in ../corrections.jsonl.', '',
              'A pass requires safe factual classification, a graph route and visible query, the exact complete answer set and raw RDF values, all answers in the response text, the required conjunction for multi-answer responses, and the correct reference entity, relation, direction and operation. No model outputs were used to alter the cases, gold answers, prompts or application code.', '',
              f"The frozen answer scorer initially counted {original['passed']} passes. A final audit of all 3,000 executed-query traces additionally rejected {len(additional)} coincidentally correct answer sets obtained from a different graph relation. The frozen score is preserved in summary.json and RESULTS.md; the stronger grounding result is recorded separately in grounded_summary.json and grounding_audit.json. This query audit was added after inference and is explicitly reported as a scoring correction, not an independently preregistered metric.", '',
              'Cases added to the failure list by the query audit:', '']
    for case in additional:
        lines.append(f"- {case['id']}: {case['input']} Expected {case['expected_property']}; observed {case['observed_plan']}. Identical answer text does not make the wrong relation correct.")
    lines += ['', 'The initial server stopped after 290 completed responses. Those responses, including failures, were preserved; the remaining 2,710 cases ran after restarting the identical model and sources. Infrastructure connection failures remain in the interrupted artifact and were not treated as model responses. No completed model answer was retried. Startup and downtime are excluded from latency. Behavioral sources and fixtures passed the final unchanged-hash checks.', '',
              'This is a factual coverage suite with 15 shared templates and uneven relation counts, not a production accuracy estimate or guardrail benchmark. Some original records appeared in earlier partial development evaluations. The corrected/replacement cases were frozen before this full run.', '',
              'Evidence: responses.jsonl, grounded_failures.jsonl, grounded_summary.json, grounding_audit.json, provenance.json, source_snapshot/, and ../gold_validation.json.']
    (out / 'BENCHMARK.md').write_text('\n'.join(lines) + '\n')
    assert digest(out / 'responses.jsonl') == source_hash
    print(json.dumps({key: summary[key] for key in ['n', 'passed', 'pass_rate', 'errors', 'frozen_answer_passed', 'additional_grounding_failures', 'latency_ms']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
