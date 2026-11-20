"""Run complete, frozen user-query regressions; never contact Speakeasy."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

import requests

from build_and_validate import HERE, ROOT, digest

sys.path.insert(0, str(ROOT / 'additional_files/src/chatbot'))
from movie_agent import MovieAgent


def semantics(plan):
    """Compare meanings, accepting equivalent year and explicit date boundaries."""
    if plan.get('operation') == 'filter':
        plan = dict(operation='select', result=plan.get('order') or 'list', filters=[
            dict(property=plan.get('property'), comparison=plan.get('comparison'), value=plan.get('value'))])
    if plan.get('operation') != 'select':
        return None
    ranges, entities = [(1, date.max.toordinal())], []
    try:
        for f in plan.get('filters', []):
            if f['property'] != 'P577':
                entities.append((f['property'], f['comparison'], f.get('entity'), f.get('value')))
                continue
            value, comparison = str(f['value']), f['comparison']
            if len(value) == 4:
                lo, hi = date(int(value), 1, 1).toordinal(), date(int(value), 12, 31).toordinal()
            else:
                lo = hi = date.fromisoformat(value).toordinal()
            condition = {'eq': [(lo, hi)], 'ne': [(1, lo - 1), (hi + 1, date.max.toordinal())],
                         'gt': [(hi + 1, date.max.toordinal())], 'gte': [(lo, date.max.toordinal())],
                         'lt': [(1, lo - 1)], 'lte': [(1, hi)]}[comparison]
            ranges = [(max(a, c), min(b, d)) for a, b in ranges for c, d in condition if max(a, c) <= min(b, d)]
    except (ValueError, KeyError, TypeError):
        return None
    return plan.get('result', 'list'), sorted(ranges), sorted(entities)


def verify(path):
    manifest = json.loads(path.read_text())
    assert digest(HERE / 'cases.jsonl') == manifest['cases_sha256']
    assert digest(ROOT / 'additional_files/data/graph.nt') == manifest['graph_sha256']
    for name, expected in manifest['source_hashes'].items():
        assert digest((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name)) == expected, name
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8002')
    parser.add_argument('--manifest', type=Path, default=HERE / 'run_manifest.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    manifest = verify(args.manifest)
    session = requests.Session()
    deadline = time.monotonic() + 180
    while True:
        try:
            health = session.get(args.url + '/health', timeout=5).json()
            if health.get('status') == 'ready':
                break
        except requests.RequestException:
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('Validation server not ready')
        time.sleep(1)
    assert all(manifest['source_hashes'][name] == h for name, h in health['source_hashes'].items())
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    (out / 'source_snapshot').mkdir()
    for name in ['movie_agent.py', 'graph_store.py', 'model_runtime.py', 'main.py', 'local_api.py']:
        shutil.copyfile((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name), out / 'source_snapshot' / name)
    (out / 'provenance.json').write_text(json.dumps(dict(manifest=manifest, server=health,
        runner_sha256=digest(Path(__file__)), note='Only natural-language input sent. Speakeasy formatting checked from actual returned model outputs without logging in or sending messages.'), indent=2) + '\n')
    rows = []
    with (out / 'responses.jsonl').open('x') as stream:
        for index, line in enumerate((HERE / 'cases.jsonl').read_text().splitlines(), 1):
            case = json.loads(line)
            started = time.perf_counter()
            http = session.post(args.url + '/chat', json={'message': case['input']}, timeout=120)
            http.raise_for_status()
            response = http.json()
            speakeasy = MovieAgent.handle_message(SimpleNamespace(chat=lambda _: response), case['input'])
            checks = dict(labels=set(response.get('labels', [])) == {'safe_in_scope'},
                          no_processing_error=not response.get('error'),
                          no_factual_prefix='The factual answer is' not in response['answer'])
            if case['kind'] == 'clarification':
                checks.update(clarification=response['route'] == 'clarification', no_query=response['query'] is None,
                              separate_questions='separate questions' in response['answer'])
            else:
                expected = {answer['value'] for answer in case['gold_answers']}
                checks.update(exact_values=set(response['values']) == expected,
                              route=response['route'] == ('knowledge_graph' if expected else 'no_answer'),
                              query_visible=bool(response['query']))
                # Complete labels are checked against accepted aliases, independent
                # of order and duplicate visible labels belonging to distinct IDs.
                accepted = {alias for a in case['gold_answers'] for alias in a['aliases']}
                checks['no_extra_names'] = set(response['answers']) <= accepted
                checks['all_names'] = all(any(alias in response['answers'] for alias in a['aliases']) for a in case['gold_answers'])
                if case['kind'] == 'selection':
                    actual_plan = response.get('query_plan', {})
                    checks['selection_semantics'] = semantics(actual_plan) == semantics(case['expected_plan'])
                    if case['expected_plan']['result'] == 'count':
                        checks['numeric_count_not_list'] = response['answer'].isdigit() and len(response['answers']) == 1
                    if len(response['answers']) > 25:
                        checks['honest_preview'] = ('This is a preview' in speakeasy and str(len(response['values'])) in speakeasy)
                    if case['expected_plan']['result'] in {'earliest', 'latest'} and len(expected) > 1:
                        checks['ties_explicit'] = 'share the' in response['answer']
                else:
                    checks['correct_lookup'] = 'wd:Q4540370 wdt:P86 ?answer' in (response['query'] or '')
            passed = all(checks.values())
            row = dict(case=case, response=response, speakeasy_answer=speakeasy, checks=checks,
                       passed=passed, latency_ms=round((time.perf_counter() - started)*1000, 2))
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(f'{index}/20 {case["id"]}: {"PASS" if passed else "FAIL"}; {len(response["values"])} values; {response["route"]}', flush=True)
    assert verify(args.manifest) == manifest
    assert session.get(args.url + '/health', timeout=10).json() == health
    summary = dict(n=len(rows), passed=sum(row['passed'] for row in rows), server=health,
                   failed_ids=[r['case']['id'] for r in rows if not r['passed']], source_and_fixtures_unchanged=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
