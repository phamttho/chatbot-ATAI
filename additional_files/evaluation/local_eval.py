"""Evaluate either implementation over HTTP with reproducible stratified samples."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import time
import requests


def select_cases(cases, args):
    if args.ids:
        wanted = set(args.ids.split(','))
        missing = wanted - {c['id'] for c in cases}
        if missing:
            raise ValueError(f'Unknown case IDs: {sorted(missing)}')
        return [c for c in cases if c['id'] in wanted]
    if args.all:
        return cases
    groups = defaultdict(list)
    for case in cases:
        groups[case.get('expected_route', case.get('expected_category'))].append(case)
    rng = random.Random(args.seed)
    return [c for key in sorted(groups) for c in rng.sample(groups[key], min(args.per_group, len(groups[key])))]


def score(case, response):
    labels = set(response.get('labels', []))
    expected = set(case.get('expected_labels', [case['expected_category']]))
    classification = labels == expected if 'expected_labels' in case else case['expected_category'] == response.get('category')
    answer = response.get('answer', '').casefold()
    category = case['expected_category']
    route = case.get('expected_route')
    if route == 'knowledge_graph':
        behavior = bool(case.get('expected_answer_terms')) and all(t.casefold() in answer for t in case['expected_answer_terms'])
        # Legacy cases are keyword checks, never advertised as complete-answer accuracy.
        if 'expected_answers' in case:
            behavior = {v.casefold() for v in response.get('answers', [])} == {v.casefold() for v in case['expected_answers']}
        behavior = behavior and response.get('route') in {'knowledge_graph', 'qwen_factual'}
    elif category == 'safe_in_scope':
        behavior = response.get('route') in {'llm_fallback', 'movie_discussion'} and bool(answer)
    else:
        behavior = response.get('route') == 'guardrail' and bool(answer)
    return dict(classification_pass=classification, behavior_pass=behavior, **{'pass': classification and behavior})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:8000')
    p.add_argument('--cases', type=Path, default=Path(__file__).with_name('test_cases.jsonl'))
    p.add_argument('--per-group', type=int, default=4)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--ids', help='Comma-separated IDs (overrides sampling)')
    p.add_argument('--all', action='store_true', help='Explicit opt-in to the full dataset')
    p.add_argument('--timeout', type=float, default=90)
    p.add_argument('--output', type=Path, default=Path(__file__).with_name('results')/'local')
    args = p.parse_args()
    if args.per_group < 1:
        p.error('--per-group must be positive')
    cases = select_cases([json.loads(l) for l in args.cases.read_text().splitlines() if l.strip()], args)
    if not cases:
        p.error('No cases selected')
    session = requests.Session()
    health = session.get(args.url+'/health', timeout=10).json()
    results = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_suffix('.jsonl').open('w') as output:
        for case in cases:
            started = time.perf_counter()
            try:
                r = session.post(args.url+'/chat', json={'message': case['input']}, timeout=args.timeout)
                r.raise_for_status()
                response = r.json()
                result = dict(case=case, response=response, **score(case, response), error=response.get('error'))
            except Exception as exc:
                result = dict(case=case, response={}, classification_pass=False, behavior_pass=False, **{'pass':False}, error=str(exc))
            result['latency_ms'] = round((time.perf_counter()-started)*1000, 2)
            results.append(result)
            output.write(json.dumps(result, ensure_ascii=False)+'\n'); output.flush()
            print(f"{case['id']}: {'PASS' if result['pass'] else 'FAIL'} {result['latency_ms']:.0f}ms", flush=True)
    groups = defaultdict(list)
    for r in results:
        c = r['case']; groups[c.get('expected_route', c['expected_category'])].append(r)
    def metrics(rows):
        return dict(n=len(rows), pass_rate=sum(bool(r['pass']) for r in rows)/len(rows), classification_accuracy=sum(r['classification_pass'] for r in rows)/len(rows), behavior_pass_rate=sum(r['behavior_pass'] for r in rows)/len(rows))
    summary = dict(timestamp=datetime.now(timezone.utc).isoformat(), server=health, seed=args.seed,
                   case_ids=[c['id'] for c in cases], cases_sha256=hashlib.sha256(args.cases.read_bytes()).hexdigest(),
                   scoring='Keyword containment for original factual cases; exact sets where expected_answers supplied; route-based refusal checks. No human safety judge.',
                   **metrics(results), groups={k:metrics(v) for k,v in groups.items()},
                   errors=sum(bool(r['error']) for r in results),
                   latency_ms={'mean':sum(r['latency_ms'] for r in results)/len(results), 'p95':sorted(r['latency_ms'] for r in results)[max(0, int(.95*len(results))-1)]})
    args.output.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
