"""Freeze additional capability cases before inference; no chatbot imports or outputs."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import re
import pyoxigraph as ox

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WD = 'http://www.wikidata.org/entity/'
WDT = 'http://www.wikidata.org/prop/direct/'
ATAI = 'http://ddis.ch/atai/'
LABEL = 'http://www.w3.org/2000/01/rdf-schema#label'
PREFIX = f'PREFIX wd: <{WD}> PREFIX wdt: <{WDT}> PREFIX atai: <{ATAI}> '
SEED = 20261108


def main():
    if (HERE/'manifest.json').exists():
        raise SystemExit('Suite already frozen; preserve it and use a new version directory.')
    graph_path = ROOT/'additional_files/data/graph.nt'
    s = ox.Store(); s.load(path=graph_path, format=ox.RdfFormat.N_TRIPLES)
    labels = defaultdict(set)
    for q in s.quads_for_pattern(None,ox.NamedNode(LABEL),None):
        if q.object.language in {None,'en'}:
            labels[q.subject.value].add(q.object.value)
    titles = defaultdict(set)
    for uri, names in labels.items():
        for name in names:
            titles[name].add(uri)
    def label(uri): return sorted(labels[uri])[0]
    def values(uri, prop):
        return list(s.quads_for_pattern(ox.NamedNode(uri),ox.NamedNode(prop),None))
    def gold(query):
        result = []
        for row in s.query(PREFIX+query):
            node = row['answer']
            if isinstance(node,ox.NamedNode):
                aa = sorted(labels[node.value])
                if not aa: raise ValueError('Unlabelled answer')
                result.append(dict(value=node.value,label=aa[0],aliases=aa,kind='entity'))
            else:
                text = node.value
                result.append(dict(value=text,label=text,aliases=[text],kind='literal'))
        return sorted(result,key=lambda a:a['value'])
    cases=[]
    def add(question, query, group, split='additional'):
        answers = gold(query)
        assert answers and len({x['label'] for x in answers})==len(answers)
        cases.append(dict(id=f'CV{len(cases)+1:03}',kind='factual',input=question,
                          relation=group,direction=group,split=split,
                          reference_query=PREFIX+query,gold_answers=answers,
                          expected_labels=['safe_in_scope']))
    add('Who is the composer of Irishman?', 'SELECT DISTINCT ?answer WHERE { wd:Q29057443 wdt:P86 ?answer . }','article_title','user_regression')
    add("How many user tags does the movie 'Pulp Fiction' have?",'SELECT (COUNT(DISTINCT ?tag) AS ?answer) WHERE { wd:Q104123 atai:tag ?tag . }','count_tags','user_regression')
    add('Which movies did not have a user rating below 9.9?','SELECT DISTINCT ?answer WHERE { ?answer atai:rating ?rating . FILTER(?rating >= 9.9) }','rating_filter','user_regression')
    # Select solely from graph coverage, never from agent success/failure.
    excluded={'The Irishman','Pulp Fiction'}
    excluded.update(a['label'] for c in map(json.loads,(HERE.parent/'quality/factual.jsonl').read_text().splitlines()) for a in c['gold_answers'] if a['kind']=='entity')
    rng=random.Random(SEED)
    pool=[]
    for uri in sorted(labels):
        if not uri.startswith(WD): continue
        title=label(uri)
        if title in excluded or len(titles[title])!=1 or not values(uri,WDT+'P577'):continue
        pool.append(uri)
    rng.shuffle(pool)
    used=set()
    # Six unseen films per capability; shared templates are explicitly recorded.
    for group in ['article_title','typo_title','count_tags','count_cast','lookup_tags','lookup_rating']:
        n=0
        for uri in pool:
            if uri in used:continue
            title=label(uri);qid=uri[len(WD):]
            if group in {'article_title','alias_title','typo_title'}:
                if not values(uri,WDT+'P86'):continue
                if group=='article_title':
                    short=re.sub(r'^(The|An|A) ','',title)
                    if short==title or len(short)<5:continue
                    # Intended referent is unique among article-stripped graph titles.
                    matches={u for t,uu in titles.items() if re.sub(r'^(The|An|A) ','',t).casefold()==short.casefold() for u in uu}
                    if matches!={uri}:continue
                    question=f'Who composed the music for {short}?'
                elif group=='alias_title':
                    aliases=[q.object.value for q in values(uri,WDT+'P1476') if isinstance(q.object,ox.Literal) and q.object.value not in labels[uri] and len(q.object.value)>=5]
                    if not aliases:continue
                    alias=sorted(aliases)[0]
                    if any(alias in names for u,names in labels.items() if u!=uri):continue
                    question=f'Who composed the music for "{alias}"?'
                else:
                    if len(title)<8 or not title[-1].isalpha():continue
                    typo=title[:-2]+title[-1]+title[-2]
                    if typo==title or typo in titles:continue
                    question=f'Who composed the score for "{typo}"?'
                query=f'SELECT DISTINCT ?answer WHERE {{ wd:{qid} wdt:P86 ?answer . }}'
            elif group in {'count_tags','lookup_tags'}:
                vv=values(uri,ATAI+'tag')
                if not 2<=len(vv)<=30:continue
                if group=='count_tags':
                    question=f'How many distinct user tags are recorded for "{title}"?'
                    query=f'SELECT (COUNT(DISTINCT ?tag) AS ?answer) WHERE {{ wd:{qid} atai:tag ?tag . }}'
                else:
                    question=f'List all user tags recorded for "{title}".'
                    query=f'SELECT DISTINCT ?answer WHERE {{ wd:{qid} atai:tag ?answer . }}'
            elif group=='count_cast':
                if not 2<=len(values(uri,WDT+'P161'))<=30:continue
                question=f'How many distinct cast members are listed for "{title}"?'
                query=f'SELECT (COUNT(DISTINCT ?actor) AS ?answer) WHERE {{ wd:{qid} wdt:P161 ?actor . }}'
            else:
                if not values(uri,ATAI+'rating'):continue
                question=f'What is the user rating of "{title}"?'
                query=f'SELECT DISTINCT ?answer WHERE {{ wd:{qid} atai:rating ?answer . }}'
            try: answer=gold(query)
            except ValueError:continue
            if not answer:continue
            add(question,query,group);used.add(uri);n+=1
            if n==6:break
        assert n==6,group
    comparisons=[('not below','>=',9.8),('at least','>=',9.7),('above','>',9.6),
                 ('greater than','>',9.85),('not above','<=',0.3),('at most','<=',0.5),
                 ('below','<',0.4),('less than','<',0.6)]
    for wording,op,threshold in comparisons:
        query=f'SELECT DISTINCT ?answer WHERE {{ ?answer atai:rating ?rating . FILTER(?rating {op} {threshold}) }}'
        add(f'Which movies have a recorded user rating {wording} {threshold}?',query,'rating_filter')
    (HERE/'factual.jsonl').write_text(''.join(json.dumps(c,ensure_ascii=False)+'\n' for c in cases))
    manifest=dict(seed=SEED,cases=len(cases),graph_sha256=hashlib.file_digest(graph_path.open('rb'),'sha256').hexdigest(),
                  factual_sha256=hashlib.sha256((HERE/'factual.jsonl').read_bytes()).hexdigest(),
                  note='Three user regressions; other fixtures selected from graph before inference, without agent outputs. Templates are coverage checks, not a production sample.')
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
