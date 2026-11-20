"""Freeze reported queries and variants using Oxigraph and independent RDFLib traversal."""
from collections import defaultdict
from datetime import date
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
PREFIX = f'PREFIX wd: <{WD}> PREFIX wdt: <{WDT}> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> '


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if (HERE / 'manifest.json').exists():
        raise SystemExit('Fixtures already frozen; preserve existing results.')
    graph_path = ROOT / 'additional_files/data/graph.nt'
    store = ox.Store()
    store.load(path=graph_path, format=ox.RdfFormat.N_TRIPLES)
    labels = defaultdict(set)
    for quad in store.quads_for_pattern(None, ox.NamedNode(str(RDFS.label)), None):
        labels[quad.subject.value].add(quad.object.value)
    nolan = [uri.removeprefix(WD) for uri, names in labels.items() if 'Christopher Nolan' in names]
    assert len(nolan) == 1
    director = nolan[0]
    def df(comparison, value):
        return dict(property='P577', comparison=comparison, value=value)
    negative = dict(property='P57', comparison='ne', entity=director)
    specs = [
        ('3. How many movies were released in 2010?', 'count', [df('eq', '2010')]),
        ('How many movies were released in 2010?', 'count', [df('eq', '2010')]),
        ('1. Which was the first film released after 2002?', 'earliest', [df('gt', '2002')]),
        ('Which was the first film released after 2002?', 'earliest', [df('gt', '2002')]),
        ('3. What was the latest movie released before 1990?', 'latest', [df('lt', '1990')]),
        ('What was the latest movie released before 1990?', 'latest', [df('lt', '1990')]),
        ('1. Which movies were released before 1990?', 'list', [df('lt', '1990')]),
        ('Which movies were released before 1990?', 'list', [df('lt', '1990')]),
        ('Which films were not directed by Christopher Nolan?', 'list', [negative]),
        ('How many movies released before 1990 were not directed by Christopher Nolan?', 'count', [df('lt', '1990'), negative]),
        ('Which movies were released during 2011?', 'list', [df('eq', '2011')]),
        ('How many films came out in 2011?', 'count', [df('eq', '2011')]),
        ('Which was the earliest movie released after 2027?', 'earliest', [df('gt', '2027')]),
        ('What was the latest film released before 2027?', 'latest', [df('lt', '2027')]),
        ('How many films were released in 1800?', 'count', [df('eq', '1800')]),
        ('Which was the first film released after 2100?', 'earliest', [df('gt', '2100')]),
        ('Which movies were released on or after 2027-03-02?', 'list', [df('gte', '2027-03-02')]),
    ]
    cases = []
    operators = {'eq': '=', 'ne': '!=', 'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<='}
    for question, result, filters in specs:
        body = '?answer wdt:P31 ?kind . VALUES ?kind { ' + ' '.join('wd:' + t for t in TYPES) + ' } '
        dated = result in {'earliest', 'latest'} or any(f['property'] == 'P577' for f in filters)
        if dated:
            body += ('?answer wdt:P577 ?recorded . '
                     'BIND(xsd:dateTime(CONCAT(SUBSTR(STR(?recorded),1,10), "T00:00:00")) AS ?when) FILTER(BOUND(?when)) ')
        for f in filters:
            if f['property'] == 'P577':
                # Independent reference: YEAR compares years directly rather than
                # copying the production compiler's start/end-of-year expansion.
                if len(f['value']) == 4:
                    body += f'FILTER(YEAR(?when) {operators[f["comparison"]]} {int(f["value"])}) '
                else:
                    body += f'FILTER(?when {operators[f["comparison"]]} "{f["value"]}T00:00:00"^^xsd:dateTime) '
            else:
                body += f'?answer wdt:P57 ?knownDirector . FILTER NOT EXISTS {{ ?answer wdt:P57 wd:{director} . }} '
        if result == 'count':
            query = f'SELECT (COUNT(DISTINCT ?answer) AS ?answerCount) WHERE {{ {body}}}'
            value = next(iter(store.query(PREFIX + query)))['answerCount'].value
            gold = [dict(value=value, label=value, aliases=[value], kind='literal')]
        else:
            if result in {'earliest', 'latest'}:
                aggregate = 'MIN' if result == 'earliest' else 'MAX'
                query = f'SELECT DISTINCT ?answer WHERE {{ {body}{{ SELECT ({aggregate}(?when) AS ?edge) WHERE {{ {body}}} }} FILTER(?when = ?edge) }}'
            else:
                query = f'SELECT DISTINCT ?answer WHERE {{ {body}}}'
            gold = []
            for row in store.query(PREFIX + query):
                uri = row['answer'].value
                aa = sorted(labels[uri])
                unlabelled = not aa
                if unlabelled:
                    aa = [f'Unlabelled graph entity ({uri.rsplit("/", 1)[-1]})']
                gold.append(dict(value=uri, label=aa[0], aliases=aa, kind='entity', unlabelled=unlabelled))
            gold.sort(key=lambda answer: answer['value'])
        cases.append(dict(id=f'SL{len(cases)+1:02}', kind='selection', input=question,
                          expected_plan=dict(operation='select', result=result, filters=filters),
                          reference_query=PREFIX + query, gold_answers=gold,
                          expected_labels=['safe_in_scope']))
    query = PREFIX + 'SELECT DISTINCT ?answer WHERE { wd:Q4540370 wdt:P86 ?answer . }'
    gold = []
    for row in store.query(query):
        aa = sorted(labels[row['answer'].value])
        gold.append(dict(value=row['answer'].value, label=aa[0], aliases=aa, kind='entity'))
    cases.append(dict(id='ME01', kind='lookup', input='Who composed the music for “&ME”?',
                      reference_query=query, gold_answers=gold, expected_labels=['safe_in_scope']))
    for index, question in enumerate([
        '1. Which movies were released before 1990?Which films were not directed by Christopher Nolan?',
        'Which films came out in 2010? Who directed Inception?',
    ], 1):
        cases.append(dict(id=f'MQ{index:02}', kind='clarification', input=question,
                          expected_labels=['safe_in_scope']))
    print('Loading RDFLib for independent graph traversal and calendar comparisons...', flush=True)
    graph = Graph().parse(graph_path, format='nt')
    films = set()
    for kind in TYPES:
        films.update(graph.subjects(URIRef(WDT + 'P31'), URIRef(WD + kind)))
    dates, directors = {}, {}
    for film in films:
        days = set()
        for value in graph.objects(film, URIRef(WDT + 'P577')):
            try:
                days.add(date.fromisoformat(str(value)[:10]))
            except ValueError:
                pass
        dates[film] = days
        directors[film] = set(graph.objects(film, URIRef(WDT + 'P57')))
    def date_matches(day, f):
        value = f['value']
        left, right = (day.year, int(value)) if len(value) == 4 else (day, date.fromisoformat(value))
        return {'eq': left == right, 'ne': left != right, 'gt': left > right,
                'gte': left >= right, 'lt': left < right, 'lte': left <= right}[f['comparison']]
    for case in cases:
        if case['kind'] == 'clarification':
            continue
        if case['kind'] == 'lookup':
            actual = {str(value) for value in graph.objects(URIRef(WD + 'Q4540370'), URIRef(WDT + 'P86'))}
        else:
            plan = case['expected_plan']
            date_filters = [f for f in plan['filters'] if f['property'] == 'P577']
            negative_filter = any(f['property'] == 'P57' for f in plan['filters'])
            matches = {}
            for film in films:
                if negative_filter and (not directors[film] or URIRef(WD + director) in directors[film]):
                    continue
                if date_filters or plan['result'] in {'earliest', 'latest'}:
                    valid = {day for day in dates[film] if all(date_matches(day, f) for f in date_filters)}
                    if not valid:
                        continue
                    matches[film] = valid
                else:
                    matches[film] = set()
            if plan['result'] == 'count':
                actual = {str(len(matches))}
            elif plan['result'] in {'earliest', 'latest'} and matches:
                extreme = (min if plan['result'] == 'earliest' else max)(day for dd in matches.values() for day in dd)
                actual = {str(film) for film, dd in matches.items() if extreme in dd}
            else:
                actual = set(map(str, matches))
        assert actual == {answer['value'] for answer in case['gold_answers']}, case['id']
        for answer in case['gold_answers']:
            if answer['kind'] == 'entity':
                actual_labels = {str(label) for label in graph.objects(URIRef(answer['value']), RDFS.label)}
                if answer.get('unlabelled'):
                    assert not actual_labels
                    assert answer['aliases'] == [f'Unlabelled graph entity ({answer["value"].rsplit("/", 1)[-1]})']
                else:
                    assert set(answer['aliases']) == actual_labels
        print(case['id'], case['input'], '=>', len(actual), 'answer values;', [a['label'] for a in case['gold_answers'][:4]], flush=True)
    assert len(cases) == 20
    (HERE / 'cases.jsonl').write_text(''.join(json.dumps(case, ensure_ascii=False) + '\n' for case in cases))
    manifest = dict(cases=len(cases), graph_sha256=digest(graph_path), cases_sha256=digest(HERE / 'cases.jsonl'),
                    validation='Oxigraph reference SPARQL vs independent RDFLib traversal/Python calendar comparisons; all answer sets and aliases verified before inference.',
                    source_hashes={p.name: digest(p) for p in (ROOT / 'additional_files/src/chatbot').glob('*.py')},
                    builder_sha256=digest(Path(__file__)),
                    note='Reported failures and authored variants; regression/development cases, not held-out accuracy.')
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('All 20 cases frozen before inference.', flush=True)


if __name__ == '__main__':
    main()
