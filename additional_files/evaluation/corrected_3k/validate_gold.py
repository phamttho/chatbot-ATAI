"""Independently check every corrected reference with RDFLib before inference."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS

from build_suite import HERE, ROOT, GRAPH, ORIGINAL, FILM_TYPES, WD, WDT, digest


def main():
    manifest = json.loads((HERE / 'manifest.json').read_text())
    assert digest(GRAPH) == manifest['graph_sha256']
    assert digest(ORIGINAL) == manifest['original_sha256']
    assert digest(HERE / 'factual.jsonl') == manifest['factual_sha256']
    assert digest(HERE / 'corrections.jsonl') == manifest['corrections_sha256']
    cases = [json.loads(l) for l in (HERE / 'factual.jsonl').read_text().splitlines()]
    assert len(cases) == len({c['id'] for c in cases}) == len({c['input'] for c in cases}) == 3000
    print('Loading independent RDFLib graph before inference...', flush=True)
    graph = Graph().parse(GRAPH, format='nt')
    film_types = {URIRef(WD + t) for t in FILM_TYPES}
    verified = []
    for index, case in enumerate(cases, 1):
        entity = URIRef(case['entity'])
        assert set(graph.objects(entity, URIRef(WDT + 'P31'))) & film_types, case['id']
        title = case['entity_label']
        assert Literal(title, lang='en') in set(graph.objects(entity, RDFS.label)) or any(
            str(label) == title for label in graph.objects(entity, RDFS.label)), case['id']
        possible = set()
        for label in graph.objects(entity, RDFS.label):
            if str(label) == title:
                possible.update(graph.subjects(RDFS.label, label))
        possible = {u for u in possible if set(graph.objects(u, URIRef(WDT + 'P31'))) & film_types}
        year = case['disambiguation_year']
        if year:
            possible = {u for u in possible if any(str(d).startswith(year + '-')
                        for d in graph.objects(u, URIRef(WDT + 'P577')))}
        assert possible == {entity}, (case['id'], possible)
        def canonical(node):
            # Oxigraph canonicalizes RDF numeric lexical forms (8.0 -> 8).
            # Compare numeric values independently, rather than parser spellings.
            if isinstance(node, Literal) and case['property'] in {'rating', 'tag'}:
                return format(Decimal(str(node)).normalize(), 'f')
            return str(node)
        actual = {canonical(row.answer) for row in graph.query(case['reference_query'])}
        assert actual == {a['value'] for a in case['gold_answers']}, case['id']
        assert actual, case['id']
        for answer in case['gold_answers']:
            if answer['kind'] == 'entity':
                valid = {str(label) for label in graph.objects(URIRef(answer['value']), RDFS.label)}
                assert set(answer['aliases']) == valid, case['id']
            else:
                assert answer['aliases'] == [answer['value']], case['id']
        verified.append(dict(id=case['id'], complete_answer_set_verified=True,
                             entity_and_title_verified=True, answer_count=len(actual)))
        if index % 500 == 0:
            print(f'Independently validated {index}/3000', flush=True)
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(), engine='RDFLib',
                  graph_sha256=digest(GRAPH), suite_sha256=digest(HERE / 'factual.jsonl'),
                  validation_script_sha256=digest(Path(__file__)), triples=len(graph),
                  verified_count=len(verified), cases=verified)
    (HERE / 'gold_validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: all 3000 complete reference answer sets and intended film entities validated.', flush=True)


if __name__ == '__main__':
    main()
