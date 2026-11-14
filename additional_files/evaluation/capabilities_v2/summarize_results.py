"""Summarize a completed comparison from its measured artifacts."""
import argparse
import json
import re
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results',type=Path)
    args=parser.parse_args()
    comparison=json.loads((args.results/'comparison.json').read_text())
    systems=comparison['systems']
    names=list(systems)
    lines=['# Capability update results','',
           'The updated and previous systems use Qwen 3.5 4B; baseline is the original Qwen 2.5 1.5B system. The update changes title retrieval, structured query planning, graph property exposure, and validated query compilation.','',
           'The original quality suite is a regression suite. The 47-case capability extension contains three supplied examples and 44 additional graph-derived cases selected before inference. All new complete gold sets were independently verified with RDFLib. These are coverage tests, not a production accuracy estimate.','',
           '| Metric | '+' | '.join(names)+' |',
           '|---|'+'---:|'*len(names)]
    for suite,title in [('factual','Original factual suite'),('guardrails','Original guardrail suite'),('capabilities','Capability extension')]:
        cells=[]
        for name in names:
            s=systems[name][suite];cells.append(f"{s['passed']}/{s['n']} ({s['pass_rate']:.1%})")
        lines.append('| '+title+' | '+' | '.join(cells)+' |')
    for split,title in [('user_regression','Supplied three regressions'),('additional','Additional capability cases')]:
        cells=[]
        for name in names:
            s=systems[name]['capabilities']['splits'][split];cells.append(f"{s['passed']}/{s['n']}")
        lines.append('| '+title+' | '+' | '.join(cells)+' |')
    lines+=['','Split rows are subsets of the capability extension, not additional tests. Guardrail success requires exact labels and correct handling; refusal handling is also reported independently in the JSON summaries.','',
            '| Capability group | '+' | '.join(names)+' |','|---|'+'---:|'*len(names)]
    for group in systems[names[0]]['capabilities']['groups']:
        lines.append('| '+group+' | '+' | '.join(f"{systems[name]['capabilities']['groups'][group]['passed']}/{systems[name]['capabilities']['groups'][group]['n']}" for name in names)+' |')
    lines+=['','| Average / p95 latency | '+' | '.join(names)+' |','|---|'+'---:|'*len(names)]
    for suite in ['factual','guardrails','capabilities']:
        cells=[]
        for name in names:
            latency=systems[name][suite]['latency_ms'];cells.append(f"{latency['mean']/1000:.2f}s / {latency['p95']/1000:.2f}s")
        lines.append('| '+suite+' | '+' | '.join(cells)+' |')
    lines+=['','## Provenance','']
    for name in names:
        for suite,s in systems[name].items():
            if 'imported_from' in s:
                lines.append(f"- {name} {suite}: reused matching traces from `{s['imported_from']}`, originally measured {s['timestamp']}.")
            else:
                lines.append(f"- {name} {suite}: measured live, completed {s['timestamp']}.")
    lines+=['','Requests were sequential on the local NVIDIA GB10; startup is excluded. Historical imported timings came from an earlier run. The source and fixture hashes are in `comparison.json`; loaded updated-server source hashes are in its health metadata. The original-suite failures were used to correct exact-label ranking and unique graph-direction handling, entity types, paired quotes, punctuation, and matched-name ambiguity before this completed run.','',
            '## Remaining updated-system factual failures','']
    failures=[]
    for suite in ['factual','capabilities']:
        for row in map(json.loads,(args.results/f'updated_{suite}.jsonl').read_text().splitlines()):
            if not row['scores']['passed']:failures.append(row)
    if not failures:lines.append('None in the evaluated factual suites.')
    for row in failures:
        case=row['case'];response=row['response']
        expected=' and '.join(a['label'] for a in case['gold_answers'])
        lines.append(f"- **{case['id']}** — {case['input']} Expected: {expected}. Route: `{response.get('route')}`. Answer: {response.get('answer','[no response]')}")
    lines+=['','Correct handling of safe controls checks admission, not open-ended response quality. Ambiguous-title clarification counts as a factual miss under the existing exact-answer rubric. Recommendations, arbitrary multi-hop queries, and conversational memory remain unsupported. Fixtures used for future fixes become regressions and need a separate new test split for the next generalization claim.','']
    tests=args.results/'tests.log'
    if tests.exists():
        log=tests.read_text();count=re.search(r'Ran (\d+) tests',log)
        if count and re.search(r'^OK$',log,re.M):
            lines.extend([f'All {count[1]} automated repository tests passed; see `tests.log`.',''])
    (args.results/'RESULTS.md').write_text('\n'.join(lines))
    print(args.results/'RESULTS.md')

if __name__=='__main__':main()
