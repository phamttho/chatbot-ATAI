import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'evaluation/quality/run_suite.py'
spec=importlib.util.spec_from_file_location('quality_scoring',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class QualityScoringTests(unittest.TestCase):
 def case(self):
  return {'gold_answers':[{'value':'wd:1','aliases':['Ann Lee','A. Lee']},{'value':'wd:2','aliases':['John Smith']}]}
 def response(self):
  return dict(labels=['safe_in_scope'],route='knowledge_graph',answers=['Ann Lee','John Smith'],query='SELECT...',answer='The factual answer is: Ann Lee and John Smith')
 def test_complete_exact_set_passes(self):
  self.assertTrue(m.score_factual(self.case(),self.response())['passed'])
 def test_missing_and_extra_entities_fail(self):
  for answers in [['Ann Lee'],['Ann Lee','John Smith','Someone Else'],['Ann','John Smith']]:
   r=self.response();r['answers']=answers
   self.assertFalse(m.score_factual(self.case(),r)['passed'])
 def test_label_aliases_are_accepted(self):
  r=self.response();r['answers']=['A. Lee','John Smith'];r['answer']='A. Lee and John Smith'
  self.assertTrue(m.score_factual(self.case(),r)['passed'])
 def test_correct_looking_model_memory_answer_is_not_grounded(self):
  r=self.response();r.update(route='llm_fallback',answers=[],query=None)
  s=m.score_factual(self.case(),r)
  self.assertTrue(s['text_contains_all_answers']);self.assertFalse(s['passed'])
 def test_missing_name_in_natural_language_fails(self):
  r=self.response();r['answer']='The factual answer is: Ann Lee'
  self.assertFalse(m.score_factual(self.case(),r)['passed'])
 def test_comma_separated_bounded_display_keeps_complete_graph_set(self):
  c={'gold_answers':[{'value':str(i),'aliases':[f'Person {i}']} for i in range(12)]}
  names=[f'Person {i}' for i in range(12)]
  r=dict(labels=['safe_in_scope'],route='knowledge_graph',answers=names,
         displayed_answers=names[:10],query='SELECT...',answer=', '.join(names[:10])+' (showing 10 of 12 matching records)')
  self.assertTrue(m.score_factual(c,r)['passed'])
  r['displayed_answers']=names[:9]
  self.assertFalse(m.score_factual(c,r)['passed'])
 def test_csv_escaped_quote_is_the_same_displayed_name(self):
  name='11\'09"01 September 11 2'
  c={'gold_answers':[{'value':'Q1','aliases':[name]}]}
  r=dict(labels=['safe_in_scope'],route='knowledge_graph',answers=[name],displayed_answers=[name],
         query='SELECT...',answer='"11\'09""01 September 11 2"')
  self.assertTrue(m.score_factual(c,r)['passed'])
 def test_multilabel_detection_and_refusal_are_separate(self):
  c=dict(expected_labels=['unsafe','out_of_scope'],expected_action='refuse')
  r=dict(labels=['unsafe'],route='guardrail',answer='I cannot help.',query=None,answers=[])
  s=m.score_guardrail(c,r)
  self.assertTrue(s['action_pass']);self.assertFalse(s['classification_pass']);self.assertFalse(s['passed'])
 def test_safe_movie_redirection_is_not_an_unsafe_refusal(self):
  c=dict(expected_labels=['safe_in_scope'],expected_action='allow')
  r=dict(labels=['safe_in_scope'],route='unsupported',answer='Ask me a factual movie question.')
  self.assertTrue(m.score_guardrail(c,r)['passed'])
  r.update(labels=['unsafe'],route='guardrail')
  self.assertFalse(m.score_guardrail(c,r)['passed'])
 def test_refusal_must_not_return_facts_or_run_queries(self):
  c=dict(expected_labels=['unsafe'],expected_action='refuse')
  r=dict(labels=['unsafe'],route='guardrail',answer='I cannot help.',query='SELECT...',answers=['a'])
  self.assertFalse(m.score_guardrail(c,r)['action_pass'])
