"""Independent RDFLib validation of graph-derived fixtures and policy schema."""
import hashlib
import json
from pathlib import Path
import re
from collections import Counter
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDFS

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def canonical(term):
 text=str(term)
 if isinstance(term,Literal) and re.match(r'^\d{4}-\d\d-\d\d(?:T|$)',text):return text[:10]
 return text


def main():
 manifest=json.loads((HERE/'manifest.json').read_text())
 graph_path=ROOT/'additional_files/data/graph.nt'
 assert hashlib.sha256(graph_path.read_bytes()).hexdigest()==manifest['graph_sha256']
 print('Loading independent RDFLib graph...',flush=True)
 g=Graph();g.parse(graph_path,format='nt')
 cases=[json.loads(l) for l in (HERE/'factual.jsonl').read_text().splitlines()]
 assert len(cases)==96 and len({c['id'] for c in cases})==96
 assert len({c['input'] for c in cases})==96
 report=[]
 for c in cases:
  expected={a['value'] for a in c['gold_answers']}
  actual={canonical(row.answer) for row in g.query(c['reference_query'])}
  assert expected==actual,(c['id'],expected,actual)
  assert actual
  for a in c['gold_answers']:
   if a['kind']=='entity':
    valid={str(label) for label in g.objects(URIRef(a['value']),RDFS.label)}
    assert set(a['aliases'])<=valid,(c['id'],a)
  # Exact movie/person labels in the question eliminate subjective entity linking
  # from reference construction; ambiguity against other film works was filtered.
  entity_labels={str(label) for label in g.objects(URIRef(c['entity']),RDFS.label)}
  assert any(label in c['input'] for label in entity_labels),(c['id'],c['input'],entity_labels)
  report.append(dict(id=c['id'],reference_verified=True,answer_count=len(actual)))
 guards=[json.loads(l) for l in (HERE/'guardrails.jsonl').read_text().splitlines()]
 valid={'safe_in_scope','unsafe','toxic','prompt_injection','out_of_scope'}
 assert len(guards)==100 and len({c['input'] for c in guards})==100
 for c in guards:
  assert set(c['expected_labels'])<=valid and c['expected_labels']
  assert (c['expected_action']=='allow')==(c['expected_labels']==['safe_in_scope'])
  assert c['rationale']
 # Both suites and the behavioural source are frozen before any requests run.
 manifest.update(factual_sha256=hashlib.sha256((HERE/'factual.jsonl').read_bytes()).hexdigest(),
                 guardrails_sha256=hashlib.sha256((HERE/'guardrails.jsonl').read_bytes()).hexdigest(),
                 guardrail_group_counts=dict(Counter(c['group'] for c in guards)),independent_reference_engine='RDFLib',
                 source_hashes={name:hashlib.sha256(((ROOT / 'additional_files/src/chatbot' / name if (ROOT / 'additional_files/src/chatbot' / name).is_file() else ROOT / 'additional_files/evaluation' / name)).read_bytes()).hexdigest() for name in ['movie_agent.py','model_runtime.py','graph_store.py','stage3_agent.py','guardrails.py','factual_qa.py','llm_client.py']})
 (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (HERE/'gold_validation.json').write_text(json.dumps(dict(triples=len(g),verified_cases=report,guardrails_schema_valid=True),indent=2)+'\n')
 print('Verified all 96 complete factual sets using independent SPARQL; policy schema validated for 100 cases.',flush=True)

if __name__=='__main__':main()
