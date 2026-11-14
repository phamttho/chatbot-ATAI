"""Validate director counts independently; retain frozen graph gold for display cases."""
import hashlib
import json
from pathlib import Path

import pyoxigraph as ox
from rdflib import Graph, URIRef
from rdflib.namespace import RDFS

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WD = 'http://www.wikidata.org/entity/'
WDT = 'http://www.wikidata.org/prop/direct/'
TYPES = ['Q11424', 'Q202866', 'Q24862', 'Q506240', 'Q17517379', 'Q226730']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    assert not (HERE / 'manifest.json').exists(), 'Preserve frozen fixtures'
    graph_path = ROOT / 'additional_files/data/graph.nt'
    graph_hash = digest(graph_path)
    store = ox.Store()
    store.load(path=graph_path, format=ox.RdfFormat.N_TRIPLES)
    # RDFLib parses every statement for the three predicates needed by these
    # counts, avoiding unrelated graph data. This is an independent RDF parser
    # and set traversal, not reuse of the production compiler or its output.
    predicates = [f' <{WDT}P31> ', f' <{WDT}P57> ', f' <{RDFS.label}> ']
    with graph_path.open() as stream:
        projection = ''.join(line for line in stream if any(p in line for p in predicates))
    independent = Graph().parse(data=projection, format='nt')
    cases = []
    for name, questions in [
        ('Christopher Nolan', ['1. How many movies did Christopher Nolan direct?',
                               'How many movies did Christopher Nolan direct?',
                               'How many films did Christopher Nolan direct?']),
        ('Martin Scorsese', ['How many movies did Martin Scorsese direct?']),
    ]:
        people = {subject for subject, label in independent.subject_objects(RDFS.label) if str(label) == name}
        assert len(people) == 1
        person = next(iter(people))
        types = {URIRef(WD + kind) for kind in TYPES}
        films = {film for film in independent.subjects(URIRef(WDT + 'P57'), person)
                 if set(independent.objects(film, URIRef(WDT + 'P31'))) & types}
        query = (f'SELECT (COUNT(DISTINCT ?film) AS ?count) WHERE {{ ?film <{WDT}P57> <{person}>; '
                 f'<{WDT}P31> ?type . VALUES ?type {{ ' + ' '.join(f'<{WD}{t}>' for t in TYPES) + ' } }')
        value = next(iter(store.query(query)))['count'].value
        assert int(value) == len(films)
        for question in questions:
            cases.append(dict(id=f'CF{len(cases)+1:02}', input=question, kind='director_count',
                              expected_count=value, entity=str(person), reference_query=query))
        print(name, value, 'distinct movie records', flush=True)
    old = HERE.parent / 'movie_selection_v4'
    assert json.loads((old / 'manifest.json').read_text())['graph_sha256'] == graph_hash
    previous = {case['id']: case for case in map(json.loads, (old / 'cases.jsonl').read_text().splitlines())}
    for case_id in ['SL04', 'SL06', 'SL02', 'ME01']:
        c = previous[case_id]
        cases.append(dict(id=f'CF{len(cases)+1:02}', input=c['input'], kind='frozen_gold',
                          gold_answers=c['gold_answers'], reference_query=c['reference_query']))
    capability = HERE.parent / 'capabilities_v2'
    assert json.loads((capability / 'manifest.json').read_text())['graph_sha256'] == graph_hash
    for c in map(json.loads, (capability / 'factual.jsonl').read_text().splitlines()):
        if c['id'] == 'CV002':
            cases.append(dict(id=f'CF{len(cases)+1:02}', input=c['input'], kind='frozen_gold',
                              gold_answers=c['gold_answers'], reference_query=c['reference_query']))
    quality = HERE.parent / 'quality'
    assert json.loads((quality / 'manifest.json').read_text())['graph_sha256'] == graph_hash
    for c in map(json.loads, (quality / 'factual.jsonl').read_text().splitlines()):
        if c['id'] == 'QF008':
            cases.append(dict(id=f'CF{len(cases)+1:02}', input=c['input'], kind='frozen_gold',
                              gold_answers=c['gold_answers'], reference_query=c['reference_query']))
    assert len(cases) == 10
    (HERE / 'cases.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases))
    manifest = dict(cases=10, graph_sha256=graph_hash, cases_sha256=digest(HERE / 'cases.jsonl'),
                    source_hashes={p.name: digest(p) for p in (ROOT / 'additional_files/src/chatbot').glob('*.py')},
                    validation='Director counts: Oxigraph SPARQL vs independent RDFLib predicate-projection traversal. Other cases reuse independently validated frozen gold with matching graph hashes.',
                    quality_scorer_sha256=digest(quality / 'run_suite.py'))
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Ten focused fixtures validated and frozen before inference.', flush=True)


if __name__ == '__main__':
    main()
