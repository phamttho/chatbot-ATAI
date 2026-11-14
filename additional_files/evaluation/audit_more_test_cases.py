"""Audit supplied fixtures against RDFLib, without importing or calling the agent."""
import collections
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS

HERE = Path(__file__).resolve().parent
GRAPH = HERE.parent / 'data/graph.nt'
CASES = HERE / 'more_test_cases.jsonl'
RELATIONS = {
    "Who directed '<TITLE>'?": 'P57',
    "Who wrote the screenplay for '<TITLE>'?": 'P58',
    "Who composed the music for '<TITLE>'?": 'P86',
    "Who was the cinematographer of '<TITLE>'?": 'P344',
    "Who edited '<TITLE>'?": 'P1040',
    "Who produced '<TITLE>'?": 'P162',
    "Who starred in '<TITLE>'?": 'P161',
    "What is the original language of '<TITLE>'?": 'P364',
    "What production company made '<TITLE>'?": 'P272',
    "Where was '<TITLE>' filmed?": 'P915',
    "Where does the story of '<TITLE>' take place?": 'P840',
    "What is the user rating of '<TITLE>'?": 'rating',
    "How many user tags does '<TITLE>' have?": 'tag',
    "What are the remakes of '<TITLE>'?": 'P4969',
    "What are the distribution platforms of '<TITLE>'?": 'P750',
}


def main():
    rows = [json.loads(line) for line in CASES.read_text().splitlines() if line.strip()]
    print('Loading independent RDFLib graph; no model requests.', flush=True)
    graph = Graph().parse(GRAPH, format='nt')
    labels = collections.defaultdict(set)
    for subject, label in graph.subject_objects(RDFS.label):
        labels[str(label)].add(subject)
    details = []
    for row in rows:
        question = row['input']
        match = re.search(r"'(.*)'", question)
        template = re.sub(r"'.*'", "'<TITLE>'", question)
        title = match[1] if match else None
        prop = RELATIONS.get(template)
        flags = []
        subjects = labels.get(title, set())
        if not subjects:
            flags.append('no_exact_title_label_requires_entity_review')
        if len(subjects) > 1:
            flags.append('multiple_exact_title_entities_requires_review')
        if not prop:
            flags.append('unmapped_question')
        values = set()
        if prop:
            predicate = URIRef(('http://ddis.ch/atai/' if prop in {'tag', 'rating'}
                                else 'http://www.wikidata.org/prop/direct/') + prop)
            for subject in subjects:
                values.update(graph.objects(subject, predicate))
        aliases = set()
        for value in values:
            if isinstance(value, Literal):
                aliases.add(str(value))
            else:
                aliases.update(str(label) for label in graph.objects(value, RDFS.label))
        terms = row.get('expected_answer_terms', [])
        if prop == 'tag':
            if terms != [str(len(values))] and subjects:
                flags.append('count_question_has_wrong_expected_count')
            if any(not re.fullmatch(r'\d+', term) for term in terms):
                flags.append('count_question_expects_non_numeric_text')
        elif subjects and prop:
            def supported(term):
                if term in aliases:
                    return True
                if prop == 'rating':
                    try:
                        return any(Decimal(term) == Decimal(value) for value in aliases)
                    except InvalidOperation:
                        return False
                return False
            if not all(supported(term) for term in terms):
                flags.append('expected_terms_not_supported_by_requested_relation')
            if not values:
                flags.append('requested_relation_has_no_values')
        # These predicates are broader than the wording; adjacency is not enough.
        if prop == 'P4969':
            flags.append('derivative_work_does_not_prove_remake')
        if prop == 'P750':
            flags.append('distributor_does_not_prove_distribution_platform')
        if not terms:
            flags.append('empty_expected_terms')
        details.append(dict(id=row['id'], input=question, property=prop,
                            exact_entities=sorted(map(str, subjects)), expected_terms=terms,
                            graph_values=sorted(map(str, values)), graph_labels=sorted(aliases),
                            flags=flags))
    duplicates = collections.defaultdict(list)
    for row in rows:
        duplicates[row['input']].append(row['id'])
    report = dict(timestamp=datetime.now(timezone.utc).isoformat(),
                  dataset_sha256=hashlib.sha256(CASES.read_bytes()).hexdigest(),
                  graph_sha256=hashlib.sha256(GRAPH.read_bytes()).hexdigest(),
                  method='Independent RDFLib relation checks; no chatbot imports or inference. Exact title labels only; missing/ambiguous titles require review. Keyword fixtures cannot establish answer completeness.',
                  total=len(rows), unique_ids=len({row['id'] for row in rows}),
                  unique_inputs=len(duplicates),
                  duplicate_inputs={q: ids for q, ids in duplicates.items() if len(ids) > 1},
                  categories=dict(collections.Counter(row['expected_category'] for row in rows)),
                  templates=dict(collections.Counter(re.sub(r"'.*'", "'<TITLE>'", row['input']) for row in rows)),
                  flag_counts=dict(collections.Counter(flag for row in details for flag in row['flags'])),
                  cases_with_flags=sum(bool(row['flags']) for row in details),
                  cases=details)
    output = HERE / 'results/more_test_cases_full_audit_20261106.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'cases'}, indent=2), flush=True)
    print(f'Full audit saved to {output}', flush=True)


if __name__ == '__main__':
    main()
