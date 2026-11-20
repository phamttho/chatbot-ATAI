"""Describe saved benchmark failures without rerunning or changing any cases."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def reason(row):
    response, case, scores = row['response'], row['case'], row['scores']
    route = response.get('route')
    error = row.get('error') or ''
    if not scores['classification_pass']:
        return 'classification'
    if route == 'error':
        if 'Entity ID was not retrieved' in error:
            return 'unretrieved_entity_id'
        if 'strongest retrieved name' in error:
            return 'entity_selection_rejected'
        if any(token in error for token in ['JSONDecodeError', 'Expected a JSON object', 'Invalid labels']):
            return 'malformed_model_output'
        return 'processing_error'
    if route == 'clarification':
        return 'clarification_instead_of_answer'
    if route in {'unsupported_query', 'unsupported'}:
        return 'unsupported_instead_of_answer'
    if route == 'no_answer':
        return 'no_answer'
    if not route:
        return 'request_failure'
    if not scores['exact_rdf_values'] or scores.get('reference_query_grounding') is False:
        plan = response.get('query_plan', {})
        if plan.get('property') != case['property']:
            return 'wrong_relation'
        if plan.get('entity') != case['entity'].rsplit('/', 1)[-1]:
            return 'wrong_entity'
        expected_operation = 'count' if case['direction'] == 'count' else 'lookup'
        if plan.get('operation') != expected_operation:
            return 'wrong_operation'
        if plan.get('direction', 'outgoing') != 'outgoing':
            return 'wrong_relation_direction'
        return 'wrong_graph_answer_set'
    return 'answer_text_or_formatting'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', type=Path)
    parser.add_argument('--grounded', action='store_true', help='Include the independently audited query-grounding gate.')
    args = parser.parse_args()
    rows = [json.loads(line) for line in (args.results / 'responses.jsonl').read_text().splitlines()]
    if args.grounded:
        audit = json.loads((args.results / 'grounding_audit.json').read_text())
        scores = {score['id']: score for score in audit['scores']}
        rows = [dict(row, scores=dict(row['scores'], passed=scores[row['case']['id']]['passed'],
                                     reference_query_grounding=scores[row['case']['id']]['reference_query_grounding'])) for row in rows]
    failed = [row for row in rows if not row['scores']['passed']]
    groups = defaultdict(list)
    for row in failed:
        groups[reason(row)].append(row)
    report = dict(completed=len(rows), failed=len(failed),
                  failure_reasons={key: len(value) for key, value in sorted(groups.items())},
                  failures_by_relation=dict(Counter(row['case']['relation'] for row in failed)),
                  cases=[dict(id=row['case']['id'], input=row['case']['input'], reason=reason(row),
                              relation=row['case']['relation'], route=row['response'].get('route'),
                              error=row.get('error'), expected=[a['label'] for a in row['case']['gold_answers']],
                              observed=row['response'].get('answers', [])) for row in failed])
    (args.results / 'failure_analysis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Failure analysis', '', f"{len(failed)} failures among {len(rows)} measured requests.", '',
             'These categories describe saved traces; no prompts, cases, gold answers, or outputs were changed.', '',
             '| Observed failure | Cases |', '|---|---:|']
    for name, subset in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        lines.append(f'| {name.replace("_", " ")} | {len(subset)} |')
    lines += ['', 'Representative examples:', '']
    for name, subset in sorted(groups.items()):
        row = subset[0]
        expected = ', '.join(a['label'] for a in row['case']['gold_answers'])
        observed = ', '.join(row['response'].get('answers', [])) or row['response'].get('route', 'request failure')
        lines.append(f"- {row['case']['id']} ({name.replace('_', ' ')}): {row['case']['input']} Expected: {expected}. Observed: {observed}.")
    (args.results / 'FAILURES.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
