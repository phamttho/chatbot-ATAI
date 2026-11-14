"""Focused live count/format checks and an explicitly offline formatting replay."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from types import SimpleNamespace

import requests

from build_cases import HERE, ROOT, digest

sys.path.insert(0, str(ROOT / 'additional_files/src/chatbot'))
from movie_agent import MovieAgent


def display_is_valid(response):
    displayed = response.get('displayed_answers', [])
    body = re.sub(r' \((?:showing \d+ of|\d+ tied).*$','',response['answer'])
    parsed = next(csv.reader([body], skipinitialspace=True))
    return (len(displayed) <= 10 and displayed == response['answers'][:10]
            and parsed == displayed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8002')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text())
    assert digest(HERE / 'cases.jsonl') == manifest['cases_sha256']
    for name, expected in manifest['source_hashes'].items():
        assert digest(ROOT / 'additional_files/src/chatbot' / name) == expected
    assert digest(HERE.parent / 'quality/run_suite.py') == manifest['quality_scorer_sha256']
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
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
    assert all(manifest['source_hashes'][k] == h for k, h in health['source_hashes'].items())
    (out / 'source_snapshot').mkdir()
    for name in ['movie_agent.py', 'graph_store.py', 'model_runtime.py', 'main.py']:
        (out / 'source_snapshot' / name).write_bytes((ROOT / 'additional_files/src/chatbot' / name).read_bytes())
    (out / 'provenance.json').write_text(json.dumps(dict(manifest=manifest, server=health,
        runner_sha256=digest(Path(__file__)), note='Ten live requests, sending only inputs. Offline replay below is separately labelled; no Speakeasy login or sends.'), indent=2) + '\n')
    rows = []
    with (out / 'live.jsonl').open('x') as stream:
        for index, line in enumerate((HERE / 'cases.jsonl').read_text().splitlines(), 1):
            case = json.loads(line)
            http = session.post(args.url + '/chat', json={'message': case['input']}, timeout=90)
            http.raise_for_status()
            response = http.json()
            speakeasy = MovieAgent.handle_message(SimpleNamespace(chat=lambda _:response),case['input'])
            checks = dict(safe=response['labels'] == ['safe_in_scope'],
                          no_error=not response.get('error'), display=display_is_valid(response),
                          graph=response['route'] == 'knowledge_graph', query=bool(response['query']))
            if case['kind'] == 'director_count':
                checks.update(numeric=response['answer'].isdigit(),
                              exact=response['answers'] == response['values'] == [case['expected_count']],
                              aggregate='COUNT(DISTINCT ?answer)' in response['query'],
                              movie_selection=response['query_plan'].get('result') == 'count',
                              requested_director=response['query_plan'].get('filters') == [
                                  dict(property='P57', comparison='eq', entity=case['entity'].rsplit('/',1)[-1])])
            else:
                checks['exact'] = set(response['values']) == {a['value'] for a in case['gold_answers']}
            row = dict(case=case, response=response, speakeasy_answer=speakeasy,
                       checks=checks, passed=all(checks.values()))
            rows.append(row)
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
            print(f'{index}/10 {case["id"]}: {"PASS" if row["passed"] else "FAIL"} {speakeasy}',flush=True)
    # Replay already-saved graph/model responses through the NEW formatter.
    # This checks the display contract, not new model inference or accuracy.
    scoring_path = HERE.parent / 'quality/run_suite.py'
    spec = importlib.util.spec_from_file_location('display_scoring', scoring_path)
    scorer = importlib.util.module_from_spec(spec);spec.loader.exec_module(scorer)
    previous = HERE.parent / 'movie_selection_v4/results_regression_243_v2'
    replay = []
    for suite in ['factual', 'guardrails', 'capabilities']:
        path = previous / f'updated_{suite}.jsonl'
        original_hash = digest(path)
        for line in path.read_text().splitlines():
            original = json.loads(line)
            response = dict(original['response'])
            if suite != 'guardrails':
                response['answer'] = MovieAgent.format_graph_answers(response['answers'], response['values'], response.get('query_plan',{}))
                response['displayed_answers'] = response['answers'][:10]
                response['answer_limit'] = 10
                passed = scorer.score_factual(original['case'],response)['passed'] and display_is_valid(response)
            else:
                passed = scorer.score_guardrail(original['case'],response)['passed']
            replay.append(dict(id=original['case']['id'],suite=suite,passed=bool(passed)))
        assert digest(path) == original_hash
    summary = dict(live=dict(n=len(rows),passed=sum(r['passed'] for r in rows)),
                   offline_format_replay=dict(n=len(replay),passed=sum(r['passed'] for r in replay),
                       note='No fresh inference: replay of v4.1 saved results under the user-requested comma/ten-item display policy.'),
                   failed_live=[r['case']['id'] for r in rows if not r['passed']],
                   failed_replay=[r for r in replay if not r['passed']],server=health)
    for name, expected in manifest['source_hashes'].items():
        assert digest(ROOT / 'additional_files/src/chatbot' / name) == expected
    assert session.get(args.url + '/health',timeout=10).json() == health
    (out / 'replay.json').write_text(json.dumps(replay,indent=2)+'\n')
    (out / 'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__ == '__main__':
    main()
