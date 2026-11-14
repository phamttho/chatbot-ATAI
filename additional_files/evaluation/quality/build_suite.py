"""Build graph-grounded factual fixtures without importing either chatbot.

Run once to freeze a suite. Gold answers are verified separately by validate_gold.py.
"""
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import re
import pyoxigraph as ox

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GRAPH=ROOT/'additional_files/data/graph.nt'
SEED=20261107
WD='http://www.wikidata.org/entity/'
WDT='http://www.wikidata.org/prop/direct/'
RDFS='http://www.w3.org/2000/01/rdf-schema#label'
PREFIX='PREFIX wd: <'+WD+'>\nPREFIX wdt: <'+WDT+'>\n'
FILM_TYPES={'Q11424','Q202866','Q24862','Q506240','Q17517379','Q226730'}
POPULAR=['Arrival','Moonlight','Spirited Away','Whiplash','Amélie','The Grand Budapest Hotel','Blade Runner','The Matrix','Alien','Titanic','Casablanca','The Godfather','Pulp Fiction','Mad Max: Fury Road','Get Out','The Social Network','The Truman Show','No Country for Old Men','La La Land','Django Unchained','Black Swan','The Shape of Water',"Pan's Labyrinth",'Memento','Her','Up','WALL-E','A Separation','The Hunt','The Lives of Others','Inside Out','Children of Men','Oldboy','City of God','Princess Mononoke','The Pianist','12 Angry Men']
# Published/prompt examples are separate regression cases, not primary test items.
EXCLUDED={'Inception','The Handmaiden','Interstellar','Manchester by the Sea','There Will Be Blood','The Father'}
TEMPLATES={
 'P57':('director', ['Who directed {t}?','Who is the director of the film {t}?','Which person directed {t}?','Tell me who directed the movie {t}.','The film {t} was directed by whom?','Name the director of {t}.']),
 'P58':('screenwriter',['Who wrote the screenplay for {t}?','Who are the screenwriters of the movie {t}?','Name everyone credited with the screenplay for {t}.','Who is credited as a screenwriter on {t}?','Whose names are listed as screenwriters for {t}?','Who scripted the film {t}?']),
 'P86':('composer',['Who composed the music for {t}?','Who is the composer of the film {t}?','Who wrote the musical score for {t}?','Name the composer credited on {t}.','Who composed the score of the movie {t}?','Which composers are credited for {t}?']),
 'P495':('country_of_origin',['What are the countries of origin of {t}?','Which countries is the film {t} from?','List every country of origin recorded for {t}.','What countries are listed as the origins of {t}?','Where does the movie {t} originate from?','Name all countries of origin of the film {t}.']),
 'P577':('release_date',['When was {t} released?','What is the release date of the film {t}?','When did the movie {t} come out?','Give the release dates listed for {t}.','On what date was {t} released?','What release date is recorded for {t}?']),
 'P166':('awards',['Which awards did the movie {t} receive?','What awards has {t} won?','Name all awards received by {t}.','List the awards recorded as received by the film {t}.','What prizes did the movie {t} win?','Which awards were given to {t}?']),
 'P161':('cast',['Who is in the cast of {t}?','Which actors are listed in the cast of the film {t}?','Name all cast members recorded for {t}.','Who starred in the movie {t}?','Who are the cast members of {t}?','List the actors credited in the cast of {t}.']),
 'P162':('producer',['Who produced {t}?','Who are the producers of the movie {t}?','Name all producers credited on {t}.','Who is credited as a producer of the film {t}?','Who are the producers credited for the movie {t}?','List the producers recorded for {t}.']),
 'P344':('cinematographer',['Who was the cinematographer of {t}?','Who was the director of photography for {t}?','Who handled the cinematography on the film {t}?','Name the cinematographer credited for {t}.','Who is credited with cinematography on {t}?','Who shot the film {t} as its cinematographer?']),
 'P1040':('editor',['Who edited {t}?','Who is the film editor of {t}?','Name everyone credited with editing {t}.','Who worked as an editor on the film {t}?','Who are the editors credited on {t}?','Which film editors are listed for {t}?']),
 'P364':('original_language',['What is the original language of {t}?','Which languages are listed as original languages of {t}?','In what language was {t} originally made?','Name all original languages recorded for {t}.','What original language is recorded for the film {t}?','Which original languages does the movie {t} have?']),
 'P136':('genre',['What genres does {t} belong to?','What is the genre of the film {t}?','List all genres recorded for {t}.','How is the film {t} classified by genre?','Which film genres are associated with {t}?','Name every genre listed for the movie {t}.']),
}


def main():
 rng=random.Random(SEED)
 s=ox.Store();s.load(path=GRAPH,format=ox.RdfFormat.N_TRIPLES)
 labels=defaultdict(list)
 for q in s.quads_for_pattern(None,ox.NamedNode(RDFS),None):
  if isinstance(q.object,ox.Literal): labels[q.subject.value].append((q.object.language or '',q.object.value))
 def aliases(uri):
  candidates=labels.get(uri,[])
  en=[text for lang,text in candidates if lang in {'','en'}]
  return sorted(set(en or [text for lang,text in candidates]))
 def label(uri):
  a=aliases(uri);return a[0] if a else None
 def vals(subject,pid):
  return sorted({q.object for q in s.quads_for_pattern(ox.NamedNode(subject),ox.NamedNode(WDT+pid),None)},key=str)
 films=set()
 for t in FILM_TYPES:
  films.update(q.subject.value for q in s.quads_for_pattern(None,ox.NamedNode(WDT+'P31'),ox.NamedNode(WD+t)))
 by_title=defaultdict(set)
 for uri in films:
  for a in aliases(uri): by_title[a].add(uri)
 # Every selected movie has a unique film label and a usable release date.
 pool=sorted(uri for uri in films if label(uri) and label(uri) not in EXCLUDED and len(by_title[label(uri)])==1 and vals(uri,'P577'))
 used_movies=set();cases=[]
 def encode(nodes):
  result=[]
  for node in nodes:
   if isinstance(node,ox.NamedNode):
    aa=aliases(node.value)
    if not aa:return None
    result.append(dict(value=node.value,label=aa[0],aliases=aa,kind='entity'))
   elif isinstance(node,ox.Literal):
    text=node.value
    if re.match(r'^\d{4}-\d\d-\d\d(?:T|$)',text):text=text[:10]
    result.append(dict(value=text,label=text,aliases=[text],kind='literal'))
   else:return None
  # Distinct RDF values, not just labels.
  return list({v['value']:v for v in result}.values())
 def add(question,query,answers,relation,direction,entity,variant,**extra):
  assert answers
  cases.append(dict(id=f'QF{len(cases)+1:03}',kind='factual',input=question,expected_labels=['safe_in_scope'],
                    relation=relation,direction=direction,entity=entity,variant=variant,
                    reference_query=PREFIX+query,gold_answers=answers,**extra))
 for pid,(name,templates) in TEMPLATES.items():
  eligible=[]
  for uri in pool:
   answer=encode(vals(uri,pid))
   if not answer or len(answer)>12 or len({a['label'] for a in answer})!=len(answer): continue
   if pid=='P577' and any(not re.fullmatch(r'\d{4}-\d\d-\d\d',a['label']) for a in answer):continue
   eligible.append((uri,answer))
  rng.shuffle(eligible)
  selected=[]
  # Two familiar titles, four random titles; at least three multi-answer cases
  # when that relation has sufficient multi-valued examples.
  familiar=[item for item in eligible if label(item[0]) in POPULAR and item[0] not in used_movies]
  selected.extend(familiar[:2])
  multi=[item for item in eligible if len(item[1])>1 and item not in selected and item[0] not in used_movies]
  for item in multi:
   if sum(len(a)>1 for _,a in selected)>=3 or len(selected)>=6:break
   selected.append(item)
  for item in eligible:
   if len(selected)>=6:break
   if item not in selected and item[0] not in used_movies:selected.append(item)
  if len(selected)!=6:raise RuntimeError(f'Insufficient cases for {pid}')
  for i,(uri,answers) in enumerate(selected):
   title=label(uri);t=f'"{title}"' if i%2==0 else title
   question=templates[i].format(t=t)
   if i in {1,4}:question='Please answer this question with a factual approach: '+question
   add(question,f'SELECT DISTINCT ?answer WHERE {{ wd:{uri[len(WD):]} wdt:{pid} ?answer . }}',answers,name,'tail',uri,i,
       familiar=title in POPULAR)
   used_movies.add(uri)
 # Reverse queries have complete short lists and only film subjects, so the
 # one-hop reference and the wording agree without an unmentioned type filter.
 people_used=set()
 for pid,relation,verb in [('P57','director','direct'),('P58','screenwriter','write the screenplay for'),('P86','composer','compose the music for'),('P161','cast','appear in')]:
  people=defaultdict(set)
  for q in s.quads_for_pattern(None,ox.NamedNode(WDT+pid),None):
   if isinstance(q.object,ox.NamedNode):people[q.object.value].add(q.subject.value)
  eligible=[]
  for person,movies in sorted(people.items()):
   if person in people_used or not (2<=len(movies)<=8) or not movies<=films or not label(person):continue
   # Person names must resolve uniquely in the complete English label index.
   named={q.subject.value for a in aliases(person) for q in s.quads_for_pattern(None,ox.NamedNode(RDFS),ox.Literal(a,language='en'))}
   named.update(q.subject.value for a in aliases(person) for q in s.quads_for_pattern(None,ox.NamedNode(RDFS),ox.Literal(a)))
   if named!={person}:continue
   if any(label(m) in EXCLUDED or not label(m) for m in movies):continue
   answer=encode([ox.NamedNode(m) for m in sorted(movies)])
   if answer and len({a['label'] for a in answer})==len(answer):eligible.append((person,answer))
  rng.shuffle(eligible)
  if len(eligible)<4:raise RuntimeError(f'Insufficient inverse {pid}')
  for i,(person,answers) in enumerate(eligible[:4]):
   name=label(person)
   roles={'P57':f'directed by {name}', 'P58':f'whose screenplay was written by {name}', 'P86':f'with music composed by {name}', 'P161':f'featuring {name}'}
   question=[f'Which films did "{name}" {verb}?',f'List all movies {roles[pid]}.',f'What films did "{name}" {verb}?',f'Please list every film {roles[pid]}.'][i]
   # Avoid ungrammatical infinitive constructions for actor participation.
   if pid=='P161':question=[f'Which movies did "{name}" appear in?',f'List every film whose cast includes {name}.',f'Which films list "{name}" as a cast member?',f'Which films list {name} as a cast member?'][i]
   add(question,f'SELECT DISTINCT ?answer WHERE {{ ?answer wdt:{pid} wd:{person[len(WD):]} . }}',answers,relation,'head',person,i)
   people_used.add(person)
 # Date extrema: all candidates have dates, and no tied extremum is selected.
 directors=defaultdict(set)
 for q in s.quads_for_pattern(None,ox.NamedNode(WDT+'P57'),None):
  if isinstance(q.object,ox.NamedNode):directors[q.object.value].add(q.subject.value)
 eligible=[]
 for person,movies in sorted(directors.items()):
  if person in people_used or not (2<=len(movies)<=15) or not movies<=films or not label(person):continue
  dated=[]
  date_types=set()
  for movie in movies:
   dates=vals(movie,'P577')
   if not dates or not label(movie):break
   for d in dates:
    if not isinstance(d,ox.Literal) or not re.match(r'^\d{4}-\d\d-\d\d',d.value):break
    try: datetime.strptime(d.value[:10],'%Y-%m-%d')
    except ValueError: break
    date_types.add(d.datatype.value)
    dated.append((d.value[:10],movie))
   else:continue
   break
  else:
   if not dated or len(date_types)!=1:continue
   lo=min(d for d,m in dated);hi=max(d for d,m in dated)
   early={m for d,m in dated if d==lo};late={m for d,m in dated if d==hi}
   if len(early)==len(late)==1 and early!=late and not any(label(m) in EXCLUDED for m in movies):
    eligible.append((person,next(iter(early)),next(iter(late))))
 rng.shuffle(eligible)
 if len(eligible)<8:raise RuntimeError('Insufficient date extrema')
 for i,(person,early,late) in enumerate(eligible[:8]):
  earliest=i<4;name=label(person);word='earliest' if earliest else 'latest';movie=early if earliest else late
  question=f'Which movie directed by "{name}" has the {word} release date?'
  add(question,f'SELECT DISTINCT ?answer WHERE {{ ?answer wdt:P57 wd:{person[len(WD):]} . ?answer wdt:P577 ?date . }} ORDER BY '+('ASC' if earliest else 'DESC')+'(?date) LIMIT 1',encode([ox.NamedNode(movie)]),'release_extremum','head_ordered',person,i)
 assert len(cases)==96
 rng.shuffle(cases)
 target=HERE/'factual.jsonl'
 target.write_text(''.join(json.dumps(c,ensure_ascii=False,sort_keys=True)+'\n' for c in cases))
 manifest=dict(seed=SEED,graph_sha256=hashlib.sha256(GRAPH.read_bytes()).hexdigest(),factual_cases=len(cases),
               relation_counts=dict(Counter(c['relation'] for c in cases)),direction_counts=dict(Counter(c['direction'] for c in cases)),
               multi_answer_cases=sum(len(c['gold_answers'])>1 for c in cases),excluded_prompt_example_titles=sorted(EXCLUDED),
               expected_answer_source='Supplied graph, independently checked by RDFLib SPARQL before model evaluation; never model memory.',
               selection='Fixed seed, two familiar/four random movie titles per relation when available, plus multi-value coverage; no agent outputs used for selection.')
 (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps(manifest,indent=2),flush=True)

if __name__=='__main__':main()
