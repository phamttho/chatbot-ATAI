"""Run all independently validated corrected cases against the unchanged HTTP agent."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
import time

import requests

from build_suite import HERE, ROOT, GRAPH, ORIGINAL, digest

sys.path.insert(0, str(HERE.parent / 'quality'))
from run_suite import score_factual, summarize


def verify():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    validation = json.loads((HERE / 'gold_validation.json').read_text())
    assert validation['verified_count'] == manifest['cases'] == 3000
    assert validation['suite_sha256'] == manifest['factual_sha256'] == digest(HERE / 'factual.jsonl')
    assert validation['graph_sha256'] == manifest['graph_sha256'] == digest(GRAPH)
    assert manifest['original_sha256'] == digest(ORIGINAL)
    assert manifest['corrections_sha256'] == digest(HERE / 'corrections.jsonl')
    for name, expected in manifest['source_hashes'].items():
        assert digest((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name)) == expected, name
    return manifest


def assert_server(health, manifest):
    assert health['status'] == 'ready' and health['engine'] == 'llm', health
    assert health['source_hashes'], 'Server must expose loaded source hashes'
    for name, expected in health['source_hashes'].items():
        assert expected == manifest['source_hashes'][name], 'Loaded server source mismatch: ' + name


def write_report(out, summary):
    s = summary
    lines = ['# Corrected 3,000-case benchmark', '',
             f"Model: {s['server']['model']} ({s['server']['device']}); all 3,000 requests ran live, sequentially through HTTP.", '',
             f"Strict passes: **{s['passed']}/{s['n']} ({100*s['pass_rate']:.2f}%)**.",
             f"Classification accuracy: {100*s['classification_accuracy']:.2f}%. API/model processing errors: {s['errors']}.",
             f"Mean / median / p95 latency: {s['latency_ms']['mean']/1000:.3f}s / {s['latency_ms']['median']/1000:.3f}s / {s['latency_ms']['p95']/1000:.3f}s.",
             f"Measured request time: {s['total_request_seconds']/60:.2f} minutes. Startup and independent data validation excluded.", '',
             '| Relation | Passed | Total | Pass rate |', '|---|---:|---:|---:|']
    for relation, group in s['groups'].items():
        lines.append(f"| {relation} | {group['passed']} | {group['n']} | {100*group['pass_rate']:.2f}% |")
    if s.get('imported_prefix_count'):
        lines += ['', f"The initial server stopped after {s['imported_prefix_count']} completed responses. Those responses, including model failures, were preserved from {s['imported_prefix_from']}. The remaining cases ran after restarting the identical model/source revision. Connection failures in the interrupted artifact are infrastructure failures and were not treated as model answers. No completed model answer was retried. Startup and downtime are excluded from request latency."]
    lines += ['', 'A pass requires safe factual classification, a graph-answer route, the exact complete answer set (no missing or extra values), matching raw RDF values, every answer in the response text, the required conjunction for multiple answers, and a visible query. Failures are retained and never replaced after inference.', '',
              'The supplied dataset was corrected before inference: all tag-count gold answers were recalculated, complete graph answer sets replaced keywords, title/year context was resolved, remake wording became derivative work, and distribution-platform wording became distributor. Of 3,000 records, 101 unresolved/duplicate/unusable records were replaced deterministically from the graph with the same relation. All replacements and original records are recorded in ../corrections.jsonl. All 3,000 intended entities and reference queries passed independent RDFLib validation before the first request.', '',
              'This is a graph-grounded factual coverage benchmark with 15 shared templates and uneven relation counts. It does not measure guardrails or establish production accuracy. Some original records had been used in earlier partial development evaluation; this is not a pristine held-out dataset. The source and prompts were unchanged throughout this run.', '',
              'See summary.json, responses.jsonl, failures.jsonl, provenance.json, and source_snapshot/ for complete evidence.']
    (out / 'RESULTS.md').write_text('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8001')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--reuse-prefix', type=Path, help='Preserve completed responses before a transport outage; never retry model failures.')
    args = parser.parse_args()
    manifest = verify()
    cases = [json.loads(line) for line in (HERE / 'factual.jsonl').read_text().splitlines()]
    assert len(cases) == len({c['id'] for c in cases}) == 3000
    session = requests.Session()
    health_response = session.get(args.url + '/health', timeout=15)
    health_response.raise_for_status()
    health = health_response.json()
    assert_server(health, manifest)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out / 'source_snapshot'
    snapshot.mkdir()
    for name in ['movie_agent.py', 'graph_store.py', 'model_runtime.py', 'local_api.py']:
        shutil.copyfile((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name), snapshot / name)
    provenance = dict(started_at=datetime.now(timezone.utc).isoformat(), url=args.url,
                      server=health, manifest=manifest,
                      validation_sha256=digest(HERE / 'gold_validation.json'),
                      benchmark_script_sha256=digest(Path(__file__)),
                      scoring_script_sha256=digest(HERE.parent / 'quality/run_suite.py'),
                      note='All cases frozen and independently validated before inference; only natural-language input is sent. Sequential requests; no model/source tuning during run.')
    rows = []
    if args.reuse_prefix:
        original_provenance = json.loads((args.reuse_prefix / 'provenance.json').read_text())
        assert original_provenance['manifest'] == manifest
        assert original_provenance['server'] == health
        assert original_provenance['scoring_script_sha256'] == provenance['scoring_script_sha256']
        previous = [json.loads(line) for line in (args.reuse_prefix / 'responses.jsonl').read_text().splitlines()]
        for index, row in enumerate(previous):
            assert row['case'] == cases[index]
            if not row['response']:
                assert row['error'], 'Only a transport outage can end the reusable prefix'
                break
            # Preserve successful and failed model outputs equally.
            checked = score_factual(row['case'], row['response'])
            checked['exact_rdf_values'] = set(row['response'].get('values', [])) == {a['value'] for a in row['case']['gold_answers']}
            checked['passed'] = bool(checked['passed'] and checked['exact_rdf_values'] and checked['query_visible'])
            assert checked == row['scores'], row['case']['id']
            rows.append(dict(row, imported_from=str(args.reuse_prefix.resolve())))
        assert rows and len(rows) < 3000
        assert not any(row['response'] for row in previous[len(rows):]), 'Later completed answers must not be silently retried'
        provenance['imported_prefix'] = dict(count=len(rows), source=str(args.reuse_prefix.resolve()),
                                             responses_sha256=digest(args.reuse_prefix / 'responses.jsonl'),
                                             original_provenance=original_provenance)
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    prefix_count = len(rows)
    started = time.perf_counter()
    with (out / 'responses.jsonl').open('x') as stream, (out / 'failures.jsonl').open('x') as failures:
        for row in rows:
            line = json.dumps(row, ensure_ascii=False) + '\n'
            stream.write(line)
            if not row['scores']['passed']:
                failures.write(line)
        stream.flush()
        failures.flush()
        for i, case in enumerate(cases[prefix_count:], prefix_count + 1):
            request_started = time.perf_counter()
            error = None
            try:
                response = session.post(args.url + '/chat', json={'message': case['input']}, timeout=90)
                response.raise_for_status()
                response = response.json()
                error = response.get('error')
            except Exception as exc:
                (out / 'transport_outage.json').write_text(json.dumps(dict(
                    case_id=case['id'], error=str(exc), timestamp=datetime.now(timezone.utc).isoformat(),
                    note='Run stopped; no fabricated model failures for subsequent cases.'), indent=2) + '\n')
                raise
            scores = score_factual(case, response)
            scores['exact_rdf_values'] = (set(response.get('values', [])) == {a['value'] for a in case['gold_answers']})
            scores['passed'] = bool(scores['passed'] and scores['exact_rdf_values'] and scores['query_visible'])
            row = dict(case=case, response=response, scores=scores, error=error,
                       measured_at=datetime.now(timezone.utc).isoformat(),
                       latency_ms=round((time.perf_counter() - request_started)*1000, 2))
            rows.append(row)
            line = json.dumps(row, ensure_ascii=False) + '\n'
            stream.write(line)
            stream.flush()
            if not scores['passed']:
                failures.write(line)
                failures.flush()
            passed = sum(r['scores']['passed'] for r in rows)
            elapsed = time.perf_counter() - started
            progress = dict(completed=i, total=3000, passed=passed, errors=sum(bool(r['error']) for r in rows),
                            elapsed_seconds=round(elapsed, 2), imported_prefix_count=prefix_count,
                            estimated_remaining_seconds=round(elapsed/(i-prefix_count)*(3000-i), 2),
                            last_case=case['id'], updated_at=datetime.now(timezone.utc).isoformat())
            temporary = out / 'progress.tmp'
            temporary.write_text(json.dumps(progress, indent=2) + '\n')
            temporary.replace(out / 'progress.json')
            if i == 1 or i % 25 == 0:
                print(json.dumps(progress), flush=True)
    verified_manifest = verify()
    assert verified_manifest == manifest
    final_health = session.get(args.url + '/health', timeout=15).json()
    assert_server(final_health, manifest)
    assert final_health == health, 'Server identity changed during benchmark'
    assert digest(HERE.parent / 'quality/run_suite.py') == provenance['scoring_script_sha256']
    assert digest(Path(__file__)) == provenance['benchmark_script_sha256']
    summary = dict(timestamp=datetime.now(timezone.utc).isoformat(), server=health,
                   suite='corrected_3k', suite_sha256=manifest['factual_sha256'],
                   graph_sha256=manifest['graph_sha256'], source_hashes=manifest['source_hashes'],
                   **summarize(rows, 'factual'), total_request_seconds=sum(r['latency_ms'] for r in rows)/1000,
                   wall_seconds=time.perf_counter() - started,
                   exact_rdf_values_rate=sum(r['scores']['exact_rdf_values'] for r in rows)/len(rows),
                   error_types=dict(Counter(r['error'].split(':')[0] for r in rows if r['error'])),
                   source_and_fixtures_unchanged=True)
    summary['imported_prefix_count'] = prefix_count
    summary['imported_prefix_from'] = str(args.reuse_prefix.resolve()) if args.reuse_prefix else None
    corrections = [json.loads(line) for line in (HERE / 'corrections.jsonl').read_text().splitlines()]
    replacements = {r['id'] for r in corrections if r['replacement']}
    summary['correction_subsets'] = {name: dict(n=len(subset), passed=sum(r['scores']['passed'] for r in subset))
        for name, subset in [('retained_subjects', [r for r in rows if r['case']['id'] not in replacements]),
                             ('replaced_records', [r for r in rows if r['case']['id'] in replacements])]}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    write_report(out, summary)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
