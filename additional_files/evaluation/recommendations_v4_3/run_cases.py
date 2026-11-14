"""Focused live recommendation/routing regressions over loopback HTTP only."""
import hashlib
import json
from pathlib import Path
import time
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    assert hashlib.sha256((HERE / 'cases.jsonl').read_bytes()).hexdigest() == manifest['cases_sha256']
    for name, expected in manifest['source_hashes'].items():
        assert hashlib.sha256(((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name)).read_bytes()).hexdigest() == expected
    session = requests.Session()
    deadline = time.monotonic() + 180
    while True:
        try:
            http = session.get('http://127.0.0.1:8001/health',timeout=3)
            http.raise_for_status();health=http.json()
            if health.get('version') == 'llm-recommendations-v4.3':break
        except requests.RequestException:pass
        if time.monotonic() >= deadline:raise RuntimeError('Updated local server not ready')
        time.sleep(1)
    assert all(manifest['source_hashes'][name] == value for name,value in health['source_hashes'].items())
    out=HERE/'results';out.mkdir(exist_ok=False)
    (out/'provenance.json').write_text(json.dumps(dict(server=health,manifest=manifest,
        note='Only natural-language input posted to localhost. No Speakeasy login or messages. Subjective recommendations have no exact-title gold and require manual review.'),indent=2)+'\n')
    rows=[]
    with (out/'responses.jsonl').open('x') as stream:
        for case in map(json.loads,(HERE/'cases.jsonl').read_text().splitlines()):
            http=session.post('http://127.0.0.1:8001/chat',json={'message':case['input']},timeout=90)
            http.raise_for_status();response=http.json()
            checks=dict(labels=set(response['labels'])==set(case['labels']),route=response['route']==case['route'],
                        calls=response['llm_calls']==case['calls'],nonempty=bool(response['answer']),no_error=not response.get('error'))
            if case['route']=='movie_discussion':
                checks.update(llm_source=response.get('answer_source')=='language_model',no_query=response['query'] is None,
                    no_graph_answers=response['answers']==[] and response['values']==[],
                    no_old_redirection='Ask me about a movie, actor, or director.' not in response['answer'])
            elif case['route']=='guardrail':
                checks.update(no_query=response['query'] is None,no_graph_answers=response['answers']==[])
            if 'answer' in case:checks['answer']=response['answer']==case['answer']
            if 'answer_count' in case:checks.update(answer_count=len(response['values'])==case['answer_count'],display_limit=len(response['displayed_answers'])==10)
            row=dict(case=case,response=response,checks=checks,passed=all(checks.values()));rows.append(row)
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
            print(case['id'], 'PASS' if row['passed'] else 'FAIL', response['answer'],flush=True)
    for name, expected in manifest['source_hashes'].items():
        assert hashlib.sha256(((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name)).read_bytes()).hexdigest() == expected
    summary=dict(n=len(rows),passed=sum(r['passed'] for r in rows),failed=[r['case']['id'] for r in rows if not r['passed']],server=health)
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
