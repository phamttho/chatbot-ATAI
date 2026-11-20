"""Compare frozen capability fixtures and the original quality suite over local HTTP."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import requests

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE.parent/'quality'))
from run_suite import score_factual, score_guardrail, summarize


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def validate_gold():
    """Second engine: validate every new answer independently using RDFLib."""
    from rdflib import Graph, URIRef
    from rdflib.namespace import RDFS
    m=json.loads((HERE/'manifest.json').read_text())
    assert digest(HERE/'factual.jsonl')==m['factual_sha256']
    assert digest(ROOT/'additional_files/data/graph.nt')==m['graph_sha256']
    print('Loading RDFLib for independent reference validation...',flush=True)
    g=Graph().parse(ROOT/'additional_files/data/graph.nt',format='nt')
    verified=[]
    for c in map(json.loads,(HERE/'factual.jsonl').read_text().splitlines()):
        actual={str(row.answer) for row in g.query(c['reference_query'])}
        assert actual=={a['value'] for a in c['gold_answers']},c['id']
        for a in c['gold_answers']:
            if a['kind']=='entity':
                assert set(a['aliases'])<={str(l) for l in g.objects(URIRef(a['value']),RDFS.label)}
        verified.append(c['id'])
    return dict(engine='RDFLib',verified_cases=verified,triples=len(g))


def run(name,url,suite,cases_path,out):
    deadline=time.monotonic()+180
    while True:
        try:
            check=requests.get(url+'/health',timeout=10)
            check.raise_for_status();health=check.json()
            if health.get('status')=='ready':break
        except requests.RequestException:
            pass
        if time.monotonic()>=deadline:
            raise RuntimeError('Server did not become ready: '+url)
        time.sleep(1)
    cases=[json.loads(l) for l in cases_path.read_text().splitlines()]
    rows=[];session=requests.Session()
    with (out/f'{name}_{suite}.jsonl').open('x') as stream:
        for i,c in enumerate(cases,1):
            start=time.perf_counter();error=None
            try:
                response=session.post(url+'/chat',json={'message':c['input']},timeout=90)
                response.raise_for_status();response=response.json();error=response.get('error')
            except Exception as exc:
                response={};error=str(exc)
            scores=(score_guardrail if suite=='guardrails' else score_factual)(c,response)
            row=dict(case=c,response=response,scores=scores,error=error,latency_ms=round((time.perf_counter()-start)*1000,2))
            rows.append(row);stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
            print(f'{name} {suite} {i}/{len(cases)} {c["id"]}: {"PASS" if scores["passed"] else "FAIL"}',flush=True)
    summary=dict(timestamp=datetime.now(timezone.utc).isoformat(),server=health,suite=suite,
                 suite_sha256=digest(cases_path),**summarize(rows,'guardrails' if suite=='guardrails' else 'factual'))
    if suite=='capabilities':
        summary['splits']={split:dict(n=len(subset),passed=sum(r['scores']['passed'] for r in subset))
                           for split in ['user_regression','additional']
                           for subset in [[r for r in rows if r['case']['split']==split]]}
    (out/f'{name}_{suite}.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--systems',nargs='+',choices=['baseline','previous','updated'],default=['baseline','previous','updated'])
    p.add_argument('--baseline-url',default='http://127.0.0.1:8000')
    p.add_argument('--previous-url',default='http://127.0.0.1:8001')
    p.add_argument('--updated-url',default='http://127.0.0.1:8002')
    p.add_argument('--reuse-results',type=Path,help='Reuse matching completed baseline/previous suites from a capability run; updated system always runs live.')
    p.add_argument('--reuse-quality',type=Path,help='Reuse original 196-case baseline/previous traces; new capabilities and updated system always run live.')
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    if args.output_dir.exists():p.error('Choose a fresh output directory')
    sources={str(f.relative_to(ROOT)):digest(f) for f in (ROOT/'additional_files/src/chatbot').glob('*.py')}
    fixtures={str(f):digest(f) for f in [HERE/'factual.jsonl',HERE.parent/'quality/factual.jsonl',HERE.parent/'quality/guardrails.jsonl']}
    validation=validate_gold()
    args.output_dir.mkdir(parents=True)
    (args.output_dir/'gold_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
    summaries={}
    for name,url in [('baseline',args.baseline_url),('previous',args.previous_url),('updated',args.updated_url)]:
        if name not in args.systems:continue
        summaries[name]={}
        for suite in ['factual','guardrails','capabilities']:
            reuse_path = args.reuse_results if name!='updated' else None
            if reuse_path or (args.reuse_quality and name!='updated' and suite!='capabilities'):
                prefix=name if reuse_path else ('baseline' if name=='baseline' else 'qwen4')
                reuse_path = reuse_path or args.reuse_quality
                for suffix in ['.jsonl','.summary.json']:
                    source=reuse_path/f'{prefix}_{suite}{suffix}'
                    target=args.output_dir/f'{name}_{suite}{suffix}'
                    shutil.copyfile(source,target)
                summary=json.loads((args.output_dir/f'{name}_{suite}.summary.json').read_text())
                case_path=HERE/'factual.jsonl' if suite=='capabilities' else HERE.parent/'quality'/f'{suite}.jsonl'
                assert summary['suite_sha256']==digest(case_path)
                rows=[json.loads(l) for l in (args.output_dir/f'{name}_{suite}.jsonl').read_text().splitlines()]
                assert [r['case'] for r in rows]==[json.loads(l) for l in case_path.read_text().splitlines()]
                summary['imported_from']=str(reuse_path.resolve())
                (args.output_dir/f'{name}_{suite}.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            else:
                case_path=HERE/'factual.jsonl' if suite=='capabilities' else HERE.parent/'quality'/f'{suite}.jsonl'
                summary=run(name,url,suite,case_path,args.output_dir)
            summaries[name][suite]=summary
    for path,expected in fixtures.items():assert digest(Path(path))==expected,'Fixture changed during evaluation'
    for path,expected in sources.items():assert digest(ROOT/path)==expected,'Source changed during evaluation'
    comparison=dict(systems=summaries,local_source_hashes=sources,fixture_hashes=fixtures,
                    note='Model requests run sequentially. Imported quality results are explicitly identified; only updated server health exposes startup source hashes.')
    (args.output_dir/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    print(json.dumps({name:{suite:dict(n=s['n'],passed=s['passed']) for suite,s in suites.items()} for name,suites in summaries.items()},indent=2),flush=True)

if __name__=='__main__':main()
