"""Contract tests with a tiny graph; no model downloads or GPU required."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_FILES = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_FILES / 'evaluation'))
sys.path.insert(1, str(PROJECT_FILES / 'src/chatbot'))
from graph_store import GraphStore, ClarificationNeeded, UnsupportedQuery, quoted_mentions
from movie_agent import MovieAgent, parse_plan
from local_api import create_app
from fastapi.testclient import TestClient

GRAPH = '''@prefix wd: <http://www.wikidata.org/entity/> .
@prefix wdt: <http://www.wikidata.org/prop/direct/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix atai: <http://ddis.ch/atai/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
wd:Q1 rdfs:label "Example Movie"; wdt:P31 wd:Q11424; wdt:P58 wd:Q2, wd:Q3; wdt:P577 "2001-01-01"^^xsd:date; wdt:P57 wd:Q2 .
wd:Q2 rdfs:label "Alice Director" . wd:Q3 rdfs:label "Bob Writer" .
wd:Q4 rdfs:label "Later Movie"; wdt:P57 wd:Q2; wdt:P577 "2004-01-01"^^xsd:date .
wd:Q5 rdfs:label "The Sample"; skos:altLabel "Sample Alias"; wdt:P86 wd:Q2; atai:tag "dark", "funny"; atai:rating "9.9"^^xsd:double .
wd:Q6 rdfs:label "Boundary High"; atai:rating "10"^^xsd:double .
wd:Q7 rdfs:label "Boundary Low"; atai:rating "9.8"^^xsd:double .
wd:Q8 rdfs:label "Unknown Rating" .
wd:Q11 rdfs:label "Sample"; wdt:P86 wd:Q3 .
wd:Q9 rdfs:label "Duplicate"; wdt:P86 wd:Q2; wdt:P577 "2001-01-01"^^xsd:date .
wd:Q10 rdfs:label "Duplicate"; wdt:P86 wd:Q3; wdt:P577 "2002-01-01"^^xsd:date .
wd:Q12 rdfs:label "Example Movie"; wdt:P31 wd:Q7725634; wdt:P577 "1998-01-01"^^xsd:date .
wd:Q13 rdfs:label "Person's Movie"; wdt:P86 wd:Q2 .
wd:Q14 rdfs:label "Up"; wdt:P364 wd:Q2 .
wd:Q15 rdfs:label "Up!"; wdt:P364 wd:Q3 .
wd:Q16 rdfs:label "The Producers"; wdt:P162 wd:Q3 .
wd:Q17 rdfs:label "Sherlock Holmes"; wdt:P162 wd:Q2 .
wd:Q18 rdfs:label "&ME"; wdt:P31 wd:Q11424; wdt:P86 wd:Q2 .
wd:Q19 rdfs:label "Date Before"; wdt:P31 wd:Q11424; wdt:P577 "2027-02-28"^^xsd:date .
wd:Q20 rdfs:label "Date On"; wdt:P31 wd:Q11424; wdt:P577 "2027-03-01"^^xsd:date .
wd:Q21 rdfs:label "Date On Time"; wdt:P31 wd:Q11424; wdt:P577 "2027-03-01T12:00:00"^^xsd:dateTime .
wd:Q22 rdfs:label "Date After"; wdt:P31 wd:Q11424; wdt:P577 "2027-03-02"^^xsd:date .
wd:Q23 rdfs:label "Date After Time"; wdt:P31 wd:Q11424; wdt:P577 "2028-04-17T00:00:00"^^xsd:dateTime .
wd:Q24 rdfs:label "No Date Film"; wdt:P31 wd:Q11424 .
wd:Q25 rdfs:label "Dated Book"; wdt:P31 wd:Q571; wdt:P577 "2030-01-01"^^xsd:date .
wd:Q26 rdfs:label "Broken Date"; wdt:P31 wd:Q11424; wdt:P577 "not-a-date" .
wdt:P162 rdfs:label "producer" . wdt:P364 rdfs:label "original language" .
wdt:P86 rdfs:label "composer" .
wdt:P58 rdfs:label "screenwriter" . wdt:P57 rdfs:label "director" . wdt:P577 rdfs:label "publication date" .
'''


class FakeRuntime:
    model_name, device = 'fake', 'cpu'
    def __init__(self, outputs):
        self.outputs, self.calls = iter(outputs), 0
    def generate(self, *args, **kwargs):
        self.calls += 1
        value = next(self.outputs)
        return value if isinstance(value, str) else json.dumps(value)


class LocalAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.tmp.name)/'test.ttl'
        cls.path.write_text(GRAPH)
        cls.graph = GraphStore(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def agent(self, outputs):
        a = MovieAgent.__new__(MovieAgent)
        a.graph, a.llm = self.graph, FakeRuntime(outputs)
        a.model_name, a.device = a.llm.model_name, a.llm.device
        return a

    def test_multivalue_answers_are_complete_and_grounded(self):
        agent = self.agent([{'labels':['safe_in_scope'], 'intent':'factual'},
                            {'operation':'lookup','entity':'Q1','property':'P58','direction':'outgoing'}])
        result = agent.chat('Who wrote Example Movie?')
        self.assertEqual(result['answers'], ['Alice Director', 'Bob Writer'])
        self.assertEqual(result['answer'], 'Alice Director, Bob Writer')
        self.assertEqual(result['llm_calls'], 2)

    def test_inverse_and_earliest_queries(self):
        candidates = self.graph.candidates('Which film did Alice Director direct?')
        answers, _ = self.graph.execute('SELECT DISTINCT ?answer WHERE { ?answer wdt:P57 wd:Q2 . }', candidates)
        self.assertEqual(answers, ['Example Movie', 'Later Movie'])
        answers, _ = self.graph.execute('SELECT DISTINCT ?answer WHERE { ?answer wdt:P57 wd:Q2 . ?answer wdt:P577 ?date . } ORDER BY ASC(?date) LIMIT 1', candidates)
        self.assertEqual(answers, ['Example Movie'])

    def test_multilabel_refusal_never_plans_or_queries(self):
        agent = self.agent([{'labels':['unsafe','out_of_scope'], 'intent':'refuse'}])
        result = agent.chat('Recommend a crime novel and help me copy crimes.')
        self.assertEqual(result['category'], 'unsafe')
        self.assertEqual(set(result['labels']), {'unsafe', 'out_of_scope'})
        self.assertEqual(result['llm_calls'], 1)
        self.assertEqual(result['route'], 'guardrail')
        self.assertIsNone(result['query'])
        self.assertIn('cannot help', result['answer'])

    def test_safe_recommendation_is_generated_by_llm_without_graph_query(self):
        from unittest.mock import patch
        agent = self.agent([dict(labels=['safe_in_scope'], intent='discussion'),
                            'Arrival (2016) is a thoughtful science-fiction film about language and first contact.'])
        with patch.object(agent.graph, 'candidates', side_effect=AssertionError('Recommendations must use the LLM')):
            result = agent.chat('1. Recommend a science-fiction movie.')
        self.assertEqual(result['route'], 'movie_discussion')
        self.assertIn('Arrival', result['answer'])
        self.assertEqual(result['answer_source'], 'language_model')
        self.assertEqual(result['llm_calls'], 2)
        self.assertIsNone(result['query'])
        self.assertEqual(result['answers'], [])

    def test_mixed_harmful_recommendation_stops_before_generation(self):
        agent = self.agent([dict(labels=['unsafe'], intent='refuse')])
        result = agent.chat('Recommend a crime movie and explain how I can copy its crimes in real life.')
        self.assertEqual(result['route'], 'guardrail')
        self.assertEqual(result['llm_calls'], 1)
        self.assertIsNone(result['query'])
        self.assertEqual(result['answers'], [])

    def test_empty_recommendation_is_an_error_not_a_fabricated_movie(self):
        agent = self.agent([dict(labels=['safe_in_scope'], intent='discussion'), ''])
        result = agent.chat('Recommend a comedy movie.')
        self.assertEqual(result['route'], 'error')
        self.assertEqual(result['labels'], ['safe_in_scope'])
        self.assertEqual(result['answers'], [])

    def test_network_updates_unknown_ids_and_limits_are_rejected(self):
        candidates = self.graph.candidates('Example Movie')
        for query in [
            'SELECT ?answer WHERE { SERVICE <http://localhost:9> { ?answer ?p ?o } }',
            'DELETE WHERE { ?s ?p ?o }',
            'SELECT DISTINCT ?answer WHERE { wd:Q999 wdt:P58 ?answer . }',
            'SELECT DISTINCT ?answer WHERE { wd:Q1 wdt:P58 ?answer . } LIMIT 1',
            'SELECT DISTINCT ?answer WHERE { wd:Q1 wdt:P58 ?answer . ?answer wdt:P577 ?date . }',
        ]:
            with self.assertRaises(ValueError, msg=query):
                self.graph.execute(query, candidates)

    def test_malformed_classifier_fails_closed(self):
        agent = self.agent([['not a plan']])
        result = agent.chat('Who wrote Example Movie?')
        self.assertEqual(result['route'], 'error')
        self.assertEqual(result['answers'], [])
        self.assertEqual(result['llm_calls'], 1)

    def test_query_failure_preserves_intent_without_hallucination(self):
        agent = self.agent([{'labels':['safe_in_scope'],'intent':'factual'}, {'operation':'lookup','entity':'Q999','property':'P58','direction':'outgoing'}])
        result = agent.chat('Who wrote Example Movie?')
        self.assertEqual(result['category'], 'safe_in_scope')
        self.assertEqual(result['route'], 'error')
        self.assertEqual(result['answers'], [])

    def test_inconsistent_classification_is_rejected(self):
        for plan in [dict(labels=['safe_in_scope'], intent='refuse'),
                     dict(labels=['invalid'], intent='factual')]:
            with self.assertRaises(ValueError):
                parse_plan(json.dumps(plan))

    def test_blocked_label_overrides_safe_portion(self):
        agent = self.agent([{'labels':['safe_in_scope','toxic'],'intent':'discussion'}])
        result = agent.chat('You are stupid, tell me about movies.')
        self.assertEqual(result['labels'], ['toxic'])
        self.assertEqual(result['route'], 'guardrail')
        self.assertEqual(result['llm_calls'], 1)

    def test_article_alias_and_typo_retrieval(self):
        for text in ['Who composed The Sample?', 'Who composed Sample Alias?', 'Who composed "The Sampl"?']:
            self.assertIn('Q5', [c['id'] for c in self.graph.candidates(text)])
        self.assertEqual(self.graph.candidates('Which movies have a rating above 9.9?'), [])

    def test_count_custom_tags_and_lookup(self):
        plan = dict(operation='count', entity='Q5', property='tag', direction='outgoing')
        agent = self.agent([dict(labels=['safe_in_scope'],intent='factual'), plan])
        result = agent.chat('How many tags does The Sample have?')
        self.assertEqual(result['answers'], ['2'])
        self.assertIn('COUNT(DISTINCT', result['query'])
        candidates = self.graph.candidates('The Sample')
        query = self.graph.compile_plan(dict(plan,operation='lookup'), candidates)
        self.assertEqual(self.graph.execute(query,candidates)[0], ['dark','funny'])

    def test_punctuation_title_is_not_discarded_as_a_stop_word(self):
        for question in ['Who composed the music for “&ME”?', 'Who composed "&ME"?',
                         "Who composed '&ME'?", 'Who composed &ME?']:
            candidates = self.graph.candidates(question)
            self.assertEqual(candidates[0]['id'], 'Q18', question)
            agent = self.agent([dict(labels=['safe_in_scope'], intent='factual'),
                                dict(operation='lookup', entity='Q18', property='P86')])
            result = agent.chat(question)
            self.assertEqual(result['answers'], ['Alice Director'])
            self.assertEqual(result['answer'], 'Alice Director')
        self.assertNotIn('Q18', [c['id'] for c in self.graph.candidates('Tell me about a movie.')])

    def test_date_filter_boundaries_and_types_match_independent_engine(self):
        from rdflib import Graph
        independent = Graph().parse(data=GRAPH, format='turtle')
        expected = {
            'gt': ['Date After', 'Date After Time'],
            'gte': ['Date After', 'Date After Time', 'Date On', 'Date On Time'],
            'lt': ['Date Before', 'Example Movie'],
            'lte': ['Date Before', 'Date On', 'Date On Time', 'Example Movie'],
            'eq': ['Date On', 'Date On Time'],
            'ne': ['Date After', 'Date After Time', 'Date Before', 'Example Movie'],
        }
        for comparison, labels in expected.items():
            query = self.graph.compile_plan(dict(operation='filter', property='P577',
                                                comparison=comparison, value='2027-03-01'), [])
            answers, values = self.graph.execute(query, [])
            self.assertEqual(answers, labels, comparison)
            reference = {str(row.answer) for row in independent.query(self.graph.expand_query(query))}
            self.assertEqual(set(values), reference, comparison)

    def test_date_filter_does_not_need_entity_and_empty_result_is_clear(self):
        for threshold, expected, route in [('2027-03-01', ['Date After', 'Date After Time'], 'knowledge_graph'),
                                           ('2100-01-01', [], 'no_answer')]:
            agent = self.agent([dict(labels=['safe_in_scope'], intent='factual'),
                                dict(operation='filter', property='P577', comparison='gt', value=threshold)])
            result = agent.chat(f'Which movies were released after {threshold}?')
            self.assertEqual(result['route'], route)
            self.assertEqual(result['answers'], expected)
            self.assertNotIn('full name', result['answer'])
            self.assertEqual(result['llm_calls'], 2)

    def test_date_filter_rejects_invalid_dates_and_query_injection(self):
        for value in ['2027-02-30', '2027-13-01', '0000-01-01', '20270301', '2027-3-1',
                      '2027-03-01T00:00:00', '2027-03-01" SERVICE <http://example.invalid>',
                      None, 20270301, True]:
            with self.assertRaises(ValueError, msg=str(value)):
                self.graph.compile_plan(dict(operation='filter', property='P577', comparison='gt', value=value), [])
        query = self.graph.compile_plan(dict(operation='filter', property='P577', comparison='gt', value='2027-03-01'), [])
        for bad in [query + ' LIMIT 1', 'SERVICE <http://example.invalid> ' + query,
                    query.replace('wdt:P577', 'wdt:P915')]:
            with self.assertRaises(ValueError):
                self.graph.execute(bad, [])

    def test_speakeasy_answers_show_all_labels_without_factual_prefix(self):
        safe = self.agent([dict(labels=['safe_in_scope'], intent='factual'),
                           dict(operation='lookup', entity='Q18', property='P86')])
        self.assertEqual(safe.handle_message('Who composed “&ME”?'), '[safe_in_scope] Alice Director')
        for labels in [['out_of_scope'], ['toxic'], ['unsafe'],
                       ['unsafe', 'out_of_scope'], ['prompt_injection', 'out_of_scope']]:
            agent = self.agent([dict(labels=labels, intent='refuse')])
            text = agent.handle_message('A blocked test request')
            for label in labels:
                self.assertIn(f'[{label}]', text)
            self.assertNotIn('The factual answer is', text)
            self.assertEqual(agent.llm.calls, 1)

    def test_rating_boundaries_and_unknown_ratings(self):
        expected = {'gte':['Boundary High','The Sample'], 'gt':['Boundary High'],
                    'lte':['Boundary Low','The Sample'], 'lt':['Boundary Low'],
                    'eq':['The Sample'], 'ne':['Boundary High','Boundary Low']}
        for comparison, answers in expected.items():
            plan = dict(operation='filter',property='rating',comparison=comparison,value=9.9)
            query = self.graph.compile_plan(plan, [])
            self.assertEqual(self.graph.execute(query,[])[0], answers)
        query = self.graph.compile_plan(dict(operation='filter',property='rating',comparison='gt',value=10),[])
        self.assertEqual(self.graph.execute(query,[])[0], [])

    def test_ambiguity_requires_clarification(self):
        agent = self.agent([dict(labels=['safe_in_scope'],intent='factual'),
                            dict(operation='lookup',entity='Q9',property='P86',direction='outgoing')])
        result = agent.chat('Who composed Duplicate?')
        self.assertEqual(result['route'], 'clarification')
        self.assertEqual(result['answers'], [])
        self.assertIsNone(result['query'])
        self.assertIn('2001',result['answer'])
        self.assertIn('2002',result['answer'])

    def test_apostrophes_and_paired_quotes(self):
        for text in ['"Person\'s Movie"', "'Person's Movie'", '“Person’s Movie”']:
            self.assertEqual(len(quoted_mentions(text)),1)
        candidates = self.graph.candidates('Who composed "Person\'s Movie"?')
        self.assertEqual(candidates[0]['id'],'Q13')
        self.assertGreater(candidates[0]['match_score'],100)

    def test_punctuation_and_role_words_do_not_create_false_ambiguity(self):
        for name,entity,expected in [('Up','Q14',['Alice Director']),('Up!','Q15',['Bob Writer'])]:
            candidates = self.graph.candidates('What is the original language of '+name+'?')
            query = self.graph.compile_plan(dict(operation='lookup',entity=entity,property='P364'),candidates)
            self.assertEqual(self.graph.execute(query,candidates)[0],expected)
        candidates = self.graph.candidates('List the producers recorded for Sherlock Holmes.')
        query = self.graph.compile_plan(dict(operation='lookup',entity='Q17',property='P162'),candidates)
        self.assertEqual(self.graph.execute(query,candidates)[0],['Alice Director'])

    def test_movie_and_book_same_title_are_distinguished(self):
        candidates = self.graph.candidates('When was Example Movie released?')
        query = self.graph.compile_plan(dict(operation='lookup',entity='Q1',property='P577'),candidates)
        self.assertEqual(self.graph.execute(query,candidates)[0],['2001-01-01'])
        with self.assertRaises(ValueError):
            self.graph.compile_plan(dict(operation='lookup',entity='Q12',property='P577'),candidates)

    def test_exact_title_beats_article_free_alias(self):
        candidates = self.graph.candidates('Who composed "Sample"?')
        query = self.graph.compile_plan(dict(operation='lookup',entity='Q11',property='P86'),candidates)
        self.assertEqual(self.graph.execute(query,candidates)[0],['Bob Writer'])

    def test_unique_graph_direction_resolves_invalid_orientation(self):
        for name,entity,direction,expected in [('Example Movie','Q1','incoming',['Alice Director']),
                                               ('Alice Director','Q2','outgoing',['Example Movie','Later Movie'])]:
            candidates = self.graph.candidates(name)
            query = self.graph.compile_plan(dict(operation='lookup',entity=entity,property='P57',direction=direction),candidates)
            self.assertEqual(self.graph.execute(query,candidates)[0],expected)

    def test_release_year_disambiguates_and_zero_count_is_valid(self):
        candidates = self.graph.candidates('Who composed Duplicate (2001)?')
        query = self.graph.compile_plan(dict(operation='lookup',entity='Q9',property='P86'),candidates)
        self.assertEqual(self.graph.execute(query,candidates)[0],['Alice Director'])
        candidates = self.graph.candidates('Example Movie')
        query = self.graph.compile_plan(dict(operation='count',entity='Q1',property='tag'),candidates)
        self.assertEqual(self.graph.execute(query,candidates)[0],['0'])

    def test_plan_rejects_injection_and_invalid_numbers(self):
        base = dict(operation='filter',property='rating',comparison='gte',value=9.9)
        for value in ['9) SERVICE <http://evil> {', 'NaN', 'Infinity', '1e-9999999', -1, 11, True, [], None]:
            with self.assertRaises((ValueError,UnsupportedQuery)):
                self.graph.compile_plan(dict(base,value=value), [])
        for plan in [dict(base,comparison='>= 0) SERVICE'),dict(base,property='tag'),
                     dict(base,query='DELETE WHERE { ?s ?p ?o }'),
                     dict(operation='lookup',entity='Q5',property='tag',direction='sideways')]:
            with self.assertRaises(ValueError):
                self.graph.compile_plan(plan, self.graph.candidates('Sample'))

    def test_count_incoming_and_precise_entity_selection(self):
        candidates = self.graph.candidates('Alice Director')
        plan = dict(operation='count',entity='Q2',property='P57',direction='incoming')
        self.assertEqual(self.graph.execute(self.graph.compile_plan(plan,candidates),candidates)[0],['2'])
        with self.assertRaises(ValueError):
            self.graph.compile_plan(dict(operation='lookup',entity='Q999',property='P57'),candidates)

    def test_missing_entity_and_unsupported_operation_messages(self):
        for question, route in [('Who composed Unfindable?', 'no_answer'),
                                ('Compare the plots of Example Movie.', 'unsupported_query')]:
            result = self.agent([dict(labels=['safe_in_scope'],intent='factual'),
                                 dict(operation='unsupported')]).chat(question)
            self.assertEqual(result['route'],route)
            self.assertEqual(result['answers'],[])

    def test_unknown_title_is_not_a_query_error_or_guardrail_refusal(self):
        agent = self.agent([dict(labels=['safe_in_scope'], intent='factual'),
                            dict(operation='lookup', property='P57', entity='Q999')])
        result = agent.chat('Who directed "An Entirely Unrecorded Title"?')
        self.assertEqual(result['labels'], ['safe_in_scope'])
        self.assertEqual(result['route'], 'no_answer')
        self.assertIsNone(result['query'])
        self.assertNotIn('error', result)
        self.assertIn('knowledge graph', result['answer'])

    def test_unsupported_plan_explanation_does_not_become_a_processing_error(self):
        agent = self.agent([dict(labels=['safe_in_scope'], intent='factual'),
                            dict(operation='unsupported', reason='The named film is not in the retrieved context.')])
        result = agent.chat('Who directed "An Entirely Unrecorded Title"?')
        self.assertEqual(result['labels'], ['safe_in_scope'])
        self.assertEqual(result['route'], 'no_answer')
        self.assertNotIn('error', result)
        self.assertIsNone(result['query'])
        self.assertNotIn('retrieved context', result['answer'])

    def test_http_contract_and_input_validation(self):
        agent = self.agent([{'labels':['out_of_scope'],'intent':'refuse'}])
        client = TestClient(create_app(agent, 'test'))
        self.assertEqual(client.get('/health').json()['device'], 'cpu')
        self.assertEqual(client.post('/chat',json={'message':'hello'}).json()['route'], 'guardrail')
        for message in ['', '   ', 'x'*4001]:
            self.assertEqual(client.post('/chat', json={'message':message}).status_code, 422)
