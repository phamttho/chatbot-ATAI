"""Adversarial/boundary fixtures for compositional movie queries; no live model."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

from rdflib import Graph

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/chatbot'))
from graph_store import GraphStore, ClarificationNeeded
from movie_agent import MovieAgent

GRAPH = '''
@prefix wd: <http://www.wikidata.org/entity/> .
@prefix wdt: <http://www.wikidata.org/prop/direct/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
wd:Q1 rdfs:label "Alice Director" . wd:Q2 rdfs:label "Bob Director" .
wdt:P57 rdfs:label "director" . wdt:P577 rdfs:label "release date" .
wd:Q10 rdfs:label "Start A"; wdt:P31 wd:Q11424; wdt:P57 wd:Q1; wdt:P577 "2010-01-02"^^xsd:date .
wd:Q11 rdfs:label "Start B"; wdt:P31 wd:Q11424; wdt:P57 wd:Q2; wdt:P577 "2010-01-02T12:00:00"^^xsd:dateTime .
wd:Q12 rdfs:label "Co-directed"; wdt:P31 wd:Q11424; wdt:P57 wd:Q1, wd:Q2; wdt:P577 "2010-06-01"^^xsd:date .
wd:Q13 rdfs:label "Unknown Director"; wdt:P31 wd:Q11424; wdt:P577 "2010-07-01"^^xsd:date .
wd:Q14 rdfs:label "Several Dates"; wdt:P31 wd:Q11424, wd:Q202866; wdt:P57 wd:Q2;
 wdt:P577 "2010-08-01"^^xsd:date, "2010-12-31"^^xsd:date, "2011-01-01"^^xsd:date .
wd:Q15 rdfs:label "End A"; wdt:P31 wd:Q11424; wdt:P57 wd:Q2; wdt:P577 "1989-12-31"^^xsd:date .
wd:Q16 rdfs:label "End B"; wdt:P31 wd:Q11424; wdt:P57 wd:Q2; wdt:P577 "1989-12-31T12:00:00"^^xsd:dateTime .
wd:Q17 rdfs:label "Older"; wdt:P31 wd:Q11424; wdt:P57 wd:Q1; wdt:P577 "1980-01-01"^^xsd:date .
wd:Q18 rdfs:label "Boundary"; wdt:P31 wd:Q11424; wdt:P57 wd:Q1; wdt:P577 "2002-12-31"^^xsd:date .
wd:Q19 rdfs:label "Undated"; wdt:P31 wd:Q11424; wdt:P57 wd:Q2 .
wd:Q20 rdfs:label "A Book"; wdt:P31 wd:Q571; wdt:P57 wd:Q2; wdt:P577 "2010-01-01"^^xsd:date .
wd:Q21 rdfs:label "Malformed Date"; wdt:P31 wd:Q11424; wdt:P577 "invalid" .
wd:Q22 wdt:P31 wd:Q11424; wdt:P57 wd:Q2; wdt:P577 "1988-01-01"^^xsd:date .
'''


class Runtime:
    model_name, device = 'fake', 'cpu'
    def __init__(self, outputs):
        self.outputs, self.calls = iter(outputs), 0
    def generate(self, *args, **kwargs):
        self.calls += 1
        return json.dumps(next(self.outputs))


class MovieSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / 'selection.ttl'
        path.write_text(GRAPH)
        cls.graph = GraphStore(path)
        cls.independent = Graph().parse(data=GRAPH, format='turtle')
        cls.people = cls.graph.candidates('Alice Director and Bob Director')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def select(self, filters, result='list'):
        query = self.graph.compile_plan(dict(operation='select', filters=filters, result=result), self.people)
        answers, values = self.graph.execute(query, self.people)
        rows = list(self.independent.query(self.graph.expand_query(query)))
        reference = {str(row['count' if result == 'count' else 'answer']) for row in rows}
        self.assertEqual(set(values), reference)
        return answers, values, query

    def test_year_count_is_distinct_and_not_a_title_list(self):
        answers, _, query = self.select([dict(property='P577', comparison='eq', value='2010')], 'count')
        self.assertEqual(answers, ['5'])
        self.assertIn('COUNT(DISTINCT ?answer)', query)

    def test_year_boundaries_and_full_year_semantics(self):
        eq, _, _ = self.select([dict(property='P577', comparison='eq', value=2010)])
        self.assertEqual(eq, ['Co-directed', 'Several Dates', 'Start A', 'Start B', 'Unknown Director'])
        after, _, _ = self.select([dict(property='P577', comparison='gt', value='2002')])
        self.assertNotIn('Boundary', after)
        before, _, _ = self.select([dict(property='P577', comparison='lt', value='1990')])
        self.assertEqual(before, ['End A', 'End B', 'Older', 'Unlabelled graph entity (Q22)'])

    def test_first_and_latest_keep_all_date_ties_after_filtering(self):
        first, _, _ = self.select([dict(property='P577', comparison='gt', value='2002')], 'earliest')
        self.assertEqual(first, ['Start A', 'Start B'])
        latest, _, _ = self.select([dict(property='P577', comparison='lt', value='1990')], 'latest')
        self.assertEqual(latest, ['End A', 'End B'])
        empty, _, _ = self.select([dict(property='P577', comparison='gt', value='2100')], 'earliest')
        self.assertEqual(empty, [])

    def test_negation_excludes_codirected_and_unknown_directors(self):
        answer, _, query = self.select([dict(property='P57', comparison='ne', entity='Q1')])
        self.assertEqual(answer, ['End A', 'End B', 'Several Dates', 'Start B', 'Undated', 'Unlabelled graph entity (Q22)'])
        self.assertIn('FILTER NOT EXISTS', query)
        combined, _, _ = self.select([dict(property='P577', comparison='eq', value='2010'),
                                     dict(property='P57', comparison='ne', entity='Q1')], 'count')
        self.assertEqual(combined, ['2'])

    def test_date_range_uses_one_recorded_date_and_zero_count_is_an_answer(self):
        answer, _, _ = self.select([dict(property='P577', comparison='gte', value='2010-12-31'),
                                    dict(property='P577', comparison='lt', value='2011-01-01')])
        self.assertEqual(answer, ['Several Dates'])
        zero, _, _ = self.select([dict(property='P577', comparison='eq', value='1900')], 'count')
        self.assertEqual(zero, ['0'])

    def test_unlabelled_records_are_counted_and_identified_explicitly(self):
        filters = [dict(property='P577', comparison='lt', value='1990')]
        count, _, _ = self.select(filters, 'count')
        self.assertEqual(count, ['4'])
        names, values, _ = self.select(filters)
        self.assertIn('Unlabelled graph entity (Q22)', names)
        self.assertIn('http://www.wikidata.org/entity/Q22', values)

    def test_selection_rejects_raw_query_injection_and_unretrieved_people(self):
        bad = [dict(operation='select', result='count', filters=[], query='SERVICE <http://example.invalid> {}'),
               dict(operation='select', result='DROP', filters=[]),
               dict(operation='select', result='list', filters=[dict(property='P577', comparison='eq', value='2010) SERVICE {}')]),
               dict(operation='select', result='list', filters=[dict(property='P57', comparison='ne', entity='Q999')]),
               dict(operation='select', result='list', filters=[dict(property='P577', comparison='eq', value=True)]),
               dict(operation='select', result='list', filters=[dict(property='P577', comparison='eq', value='2010')] * 5)]
        for plan in bad:
            with self.assertRaises(ValueError, msg=str(plan)):
                self.graph.compile_plan(plan, self.people)
        _, _, query = self.select([dict(property='P577', comparison='eq', value='2010')], 'count')
        for tampered in [query + ' LIMIT 1', query.replace('wdt:P577', 'wdt:P915')]:
            with self.assertRaises(ValueError):
                self.graph.execute(tampered, self.people)

    def test_multiple_questions_request_separate_inputs(self):
        with self.assertRaisesRegex(ClarificationNeeded, 'separate questions'):
            self.graph.compile_plan(dict(operation='clarify', reason='multiple_questions'), [])

    def test_plain_count_and_large_list_preview_use_real_result_types(self):
        agent = MovieAgent.__new__(MovieAgent)
        agent.graph = self.graph
        agent.llm = Runtime([dict(labels=['safe_in_scope'], intent='factual'),
                             dict(operation='select', result='count', filters=[dict(property='P577', comparison='eq', value='2010')])])
        self.assertEqual(agent.handle_message('How many movies were released in 2010?'), '[safe_in_scope] 5')
        names = [f'Title {i}' for i in range(30)]
        agent.chat = lambda _: dict(labels=['safe_in_scope'], query_plan=dict(operation='select', result='list'),
                                    answers=names, values=list(range(30)),
                                    answer=MovieAgent.format_graph_answers(names, list(range(30)), dict(operation='select', result='list')))
        preview = agent.handle_message('List the films')
        self.assertIn('showing 10 of 30 matching records', preview)
        self.assertIn('Title 0, Title 1', preview)
        self.assertNotIn('Title 10', preview)
        self.assertNotIn('Title 29', preview)

    def test_tied_extremes_are_explicit_and_never_arbitrarily_reduced(self):
        agent = MovieAgent.__new__(MovieAgent)
        agent.graph = self.graph
        agent.llm = Runtime([dict(labels=['safe_in_scope'], intent='factual'),
                             dict(operation='select', result='earliest', filters=[dict(property='P577', comparison='gt', value='2002')])])
        result = agent.chat('Which was the first film released after 2002?')
        self.assertEqual(result['answers'], ['Start A', 'Start B'])
        self.assertEqual(result['answer'], 'Start A, Start B (2 tied earliest matches)')

    def test_movie_count_is_enforced_when_model_proposes_inverse_lookup(self):
        agent = MovieAgent.__new__(MovieAgent)
        agent.graph = self.graph
        agent.llm = Runtime([dict(labels=['safe_in_scope'], intent='factual'),
                             dict(operation='lookup', property='P57', entity='Q1', direction='incoming')])
        result = agent.chat('1. How many movies did Alice Director direct?')
        self.assertEqual(result['answers'], ['4'])
        self.assertEqual(result['answer'], '4')
        self.assertEqual(result['query_plan']['result'], 'count')
        self.assertEqual(result['original_query_plan']['operation'], 'lookup')
        self.assertIn('COUNT(DISTINCT', result['query'])

    def test_count_guard_does_not_count_words_inside_quoted_titles_or_tags(self):
        plan = dict(operation='lookup', entity='Q1', property='P57', direction='incoming')
        self.assertEqual(MovieAgent.enforce_movie_count('Who directed "How Many Movies"?', plan, []), plan)
        self.assertEqual(MovieAgent.enforce_movie_count('How many user tags does a movie have?', plan, []), plan)

    def test_count_guard_corrects_list_result_without_losing_filters(self):
        plan = dict(operation='select', result='list', filters=[dict(property='P577', comparison='eq', value='2010')])
        corrected = MovieAgent.enforce_movie_count('How many films were released in 2010?', plan, [])
        self.assertEqual(corrected, dict(plan, result='count'))
        self.assertEqual(plan['result'], 'list')

    def test_commas_inside_titles_are_quoted(self):
        self.assertEqual(MovieAgent.format_graph_answers(['One, Two', 'Other'], ['Q1', 'Q2'], {}), '"One, Two", Other')
