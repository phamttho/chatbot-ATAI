"""Run frozen reported-question and policy regressions over local HTTP only."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
import time
from types import SimpleNamespace

import requests

from build_and_validate import HERE, ROOT, digest

sys.path.insert(0, str(ROOT / 'additional_files/src/chatbot'))
from movie_agent import MovieAgent


def verify(path):
    manifest = json.loads(path.read_text())
    assert digest(HERE / 'cases.jsonl') == manifest['cases_sha256']
    assert digest(ROOT / 'additional_files/data/graph.nt') == manifest['graph_sha256']
    for name, expected in manifest['source_hashes'].items():
        assert digest((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name)) == expected, name
    assert len(manifest['independently_verified_factual']) == 10
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8002')
    parser.add_argument('--manifest', type=Path, default=HERE / 'manifest.json')
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
            raise RuntimeError('Validation server did not become ready')
        time.sleep(1)
    for name, expected in health['source_hashes'].items():
        assert expected == manifest['source_hashes'][name]
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    (out / 'source_snapshot').mkdir()
    for name in ['movie_agent.py', 'graph_store.py', 'model_runtime.py', 'main.py', 'local_api.py']:
        shutil.copyfile((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name), out / 'source_snapshot' / name)
    (out / 'provenance.json').write_text(json.dumps(dict(server=health, manifest=manifest,
        runner_sha256=digest(Path(__file__)), note='Only input is sent to HTTP. Speakeasy text is rendered from the real model response using its production formatter; no Speakeasy login or send.'), indent=2) + '\n')
    cases = [json.loads(line) for line in (HERE / 'cases.jsonl').read_text().splitlines()]
    rows = []
    with (out / 'responses.jsonl').open('x') as stream:
        for index, case in enumerate(cases, 1):
            started = time.perf_counter()
            http = session.post(args.url + '/chat', json={'message': case['input']}, timeout=90)
            http.raise_for_status()
            response = http.json()
            speakeasy = MovieAgent.handle_message(SimpleNamespace(chat=lambda _: response), case['input'])
            label_pass = set(response['labels']) == set(case['expected_labels'])
            display_pass = all('[' + label + ']' in speakeasy for label in case['expected_labels'])
            if case['kind'] == 'guardrail':
                if case['expected_action'] == 'refuse':
                    action_pass = (response['route'] == 'guardrail' and bool(response['answer'])
                                   and not response['answers'] and response['query'] is None
                                   and response['llm_calls'] == 1)
                else:
                    action_pass = response['route'] not in {'guardrail', 'error'} and bool(response['answer'])
                scores = dict(labels=label_pass, action=action_pass, displayed_labels=display_pass)
            else:
                expected = {answer['value'] for answer in case['gold_answers']}
                exact = set(response['values']) == expected
                text_complete = all(any(alias in response['answer'] for alias in answer['aliases'])
                                    for answer in case['gold_answers'])
                route = response['route'] == ('knowledge_graph' if expected else 'no_answer')
                plan = response.get('query_plan', {})
                if case['relation'] == 'release_date_filter':
                    comparison = re.search(r'([<>!=]+) "(\d{4}-\d{2}-\d{2})T', case['reference_query'])
                    names = {'>': 'gt', '>=': 'gte', '<': 'lt', '<=': 'lte', '=': 'eq', '!=': 'ne'}
                    grounded = (plan.get('operation') == 'filter' and plan.get('property') == 'P577'
                                and plan.get('comparison') == names[comparison[1]] and plan.get('value') == comparison[2])
                else:
                    reference_entity = re.search(r'(?:wd:|<http://www.wikidata.org/entity/)(Q\d+)', case['reference_query'])[1]
                    reference_property = re.search(r'wdt:(P\d+)', case['reference_query'])[1]
                    grounded = bool(re.search(r'WHERE\s*\{\s*wd:' + reference_entity + r'\s+wdt:' + reference_property + r'\s+\?answer', response.get('query') or ''))
                scores = dict(labels=label_pass, displayed_labels=display_pass, exact_values=exact,
                              text_complete=text_complete, route=route, query_visible=bool(response.get('query')),
                              grounded_plan=grounded, plain_answer='The factual answer is' not in response['answer'])
            passed = all(scores.values()) and not response.get('error')
            row = dict(case=case, response=response, speakeasy_answer=speakeasy,
                       scores=scores, passed=passed, latency_ms=round((time.perf_counter() - started)*1000, 2))
            rows.append(row)
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(f'{index}/20 {case["id"]}: {"PASS" if passed else "FAIL"} {speakeasy}', flush=True)
    assert verify(args.manifest) == manifest
    assert session.get(args.url + '/health', timeout=10).json() == health
    summary = dict(timestamp=datetime.now(timezone.utc).isoformat(), n=len(rows), passed=sum(r['passed'] for r in rows),
                   groups={kind: dict(n=len(rr), passed=sum(r['passed'] for r in rr))
                           for kind in ['factual', 'guardrail'] for rr in [[r for r in rows if r['case']['kind'] == kind]]},
                   server=health, source_and_fixtures_unchanged=True)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
