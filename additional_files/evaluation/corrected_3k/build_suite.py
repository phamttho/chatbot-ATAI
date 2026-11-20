"""Correct all 3,000 supplied rows using graph facts, before any inference."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re

import pyoxigraph as ox

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GRAPH = ROOT / 'additional_files/data/graph.nt'
ORIGINAL = HERE.parent / 'more_test_cases.jsonl'
WD = 'http://www.wikidata.org/entity/'
WDT = 'http://www.wikidata.org/prop/direct/'
ATAI = 'http://ddis.ch/atai/'
LABEL = 'http://www.w3.org/2000/01/rdf-schema#label'
PREFIX = f'PREFIX wd: <{WD}> PREFIX wdt: <{WDT}> PREFIX atai: <{ATAI}> '
FILM_TYPES = {'Q11424', 'Q202866', 'Q24862', 'Q506240', 'Q17517379', 'Q226730'}
SEED = 2026110603
SPECS = {
    "Who directed '<TITLE>'?": ('director', 'P57', 'Who directed {title}?'),
    "Who wrote the screenplay for '<TITLE>'?": ('screenwriter', 'P58', 'Who wrote the screenplay for {title}?'),
    "Who composed the music for '<TITLE>'?": ('composer', 'P86', 'Who composed the music for {title}?'),
    "Who was the cinematographer of '<TITLE>'?": ('cinematographer', 'P344', 'Who was the cinematographer of {title}?'),
    "Who edited '<TITLE>'?": ('editor', 'P1040', 'Who edited {title}?'),
    "Who produced '<TITLE>'?": ('producer', 'P162', 'Who produced {title}?'),
    "Who starred in '<TITLE>'?": ('cast', 'P161', 'Who starred in {title}?'),
    "What is the original language of '<TITLE>'?": ('original_language', 'P364', 'What is the original language of {title}?'),
    "What production company made '<TITLE>'?": ('production_company', 'P272', 'What production companies made {title}?'),
    "Where was '<TITLE>' filmed?": ('filming_location', 'P915', 'Where was {title} filmed?'),
    "Where does the story of '<TITLE>' take place?": ('narrative_location', 'P840', 'Where does the story of {title} take place?'),
    "What is the user rating of '<TITLE>'?": ('user_rating', 'rating', 'What is the user rating of {title}?'),
    "How many user tags does '<TITLE>' have?": ('count_tags', 'tag', 'How many distinct user tags are recorded for {title}?'),
    "What are the remakes of '<TITLE>'?": ('derivative_work', 'P4969', 'What derivative works of {title} are recorded in the graph?'),
    "What are the distribution platforms of '<TITLE>'?": ('distributor', 'P750', 'What distributors are recorded for {title}?'),
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if (HERE / 'manifest.json').exists():
        raise SystemExit('Suite already frozen; preserve it.')
    store = ox.Store()
    store.load(path=GRAPH, format=ox.RdfFormat.N_TRIPLES)
    labels = defaultdict(set)
    titles = defaultdict(set)
    for q in store.quads_for_pattern(None, ox.NamedNode(LABEL), None):
        if isinstance(q.object, ox.Literal):
            labels[q.subject.value].add(q.object.value)
            titles[q.object.value].add(q.subject.value)
    films = set()
    for film_type in FILM_TYPES:
        films.update(q.subject.value for q in store.quads_for_pattern(
            None, ox.NamedNode(WDT + 'P31'), ox.NamedNode(WD + film_type)))

    def values(uri, prop):
        predicate = (ATAI if prop in {'tag', 'rating'} else WDT) + prop
        return {q.object for q in store.quads_for_pattern(ox.NamedNode(uri), ox.NamedNode(predicate), None)}

    def years(uri):
        return {v.value[:4] for v in values(uri, 'P577') if isinstance(v, ox.Literal)}

    def referent(uri):
        """Produce a graph label and optional year with one intended film referent."""
        for title in sorted(labels[uri], key=lambda t: (len(t), t)):
            possible = titles[title] & films
            if possible == {uri}:
                return title, None
            for year in sorted(years(uri)):
                if {u for u in possible if year in years(u)} == {uri}:
                    return title, year
        return None

    def encode(nodes):
        answers = []
        for node in sorted(nodes, key=str):
            if isinstance(node, ox.NamedNode):
                aliases = sorted(labels[node.value])
                if not aliases:
                    return None
                answers.append(dict(value=node.value, label=aliases[0], aliases=aliases, kind='entity'))
            elif isinstance(node, ox.Literal):
                answers.append(dict(value=node.value, label=node.value, aliases=[node.value], kind='literal'))
            else:
                return None
        owner = {}
        for answer in answers:
            for alias in answer['aliases']:
                if alias.casefold() in owner and owner[alias.casefold()] != answer['value']:
                    return None
                owner[alias.casefold()] = answer['value']
        return answers

    # A deterministic graph-only fallback for unresolved, unsupported or duplicate
    # source records. It preserves the original relation coverage, not model wins.
    pools = {}
    rng = random.Random(SEED)
    for prop in sorted({spec[1] for spec in SPECS.values()}):
        pool = sorted(u for u in films if labels[u] and values(u, prop))
        rng.shuffle(pool)
        pools[prop] = iter(pool)
    rows = [json.loads(line) for line in ORIGINAL.read_text().splitlines() if line.strip()]
    assert len(rows) == 3000 and len({r['id'] for r in rows}) == 3000
    cases, changes, used = [], [], set()
    for row in rows:
        old_title = re.search(r"'(.*)'", row['input'])[1]
        template = re.sub(r"'.*'", "'<TITLE>'", row['input'])
        relation, prop, wording = SPECS[template]
        possible = titles[old_title] & films
        reasons = ['complete_graph_answer_set', 'explicit_film_context_and_paired_quotes']
        if not possible:
            year_match = re.fullmatch(r'(.*) \((\d{4})\)', old_title)
            if year_match:
                possible = {u for u in titles[year_match[1]] & films if year_match[2] in years(u)}
                if possible:
                    reasons.append('resolved_title_year_suffix')
        entity = next(iter(possible)) if len(possible) == 1 else None
        if len(possible) > 1:
            reasons.append('ambiguous_original_film_title')
        if not possible:
            reasons.append('unresolved_original_film_title')
        count = relation == 'count_tags'
        if count:
            reasons.append('replace_tag_text_with_distinct_count')
        if prop == 'P4969':
            reasons.append('replace_remake_claim_with_derivative_work_relation')
        if prop == 'P750':
            reasons.append('replace_platform_claim_with_distributor_relation')

        def usable(uri):
            if not uri or (uri, prop) in used or not referent(uri):
                return False
            vv = values(uri, prop)
            return bool(vv) and (count or bool(encode(vv)))

        if not usable(entity):
            reasons.append('graph_only_same_relation_replacement')
            if entity and (entity, prop) in used:
                reasons.append('duplicate_entity_relation')
            entity = next((u for u in pools[prop] if usable(u)), None)
            if entity is None:
                raise ValueError(f'No eligible replacement: {row["id"]}, {prop}')
        title, year = referent(entity)
        mention = 'the film ' + ('“' + title + '”' if '"' in title else '"' + title + '"')
        if year:
            mention += f' released in {year}'
            reasons.append('add_release_year_disambiguation')
        question = wording.format(title=mention)
        qid = entity.removeprefix(WD)
        predicate = ('atai:' if prop in {'tag', 'rating'} else 'wdt:') + prop
        if count:
            query = f'SELECT (COUNT(DISTINCT ?value) AS ?answer) WHERE {{ wd:{qid} {predicate} ?value . }}'
        else:
            query = f'SELECT DISTINCT ?answer WHERE {{ wd:{qid} {predicate} ?answer . }}'
        gold = encode({r['answer'] for r in store.query(PREFIX + query)})
        assert gold
        used.add((entity, prop))
        cases.append(dict(id=row['id'], kind='factual', input=question, relation=relation,
                          property=prop, direction='count' if count else 'outgoing',
                          entity=entity, entity_label=title, disambiguation_year=year,
                          expected_labels=['safe_in_scope'], reference_query=PREFIX + query,
                          gold_answers=gold))
        changes.append(dict(id=row['id'], original=row, corrected_input=question,
                            entity=entity, reasons=reasons,
                            replacement='graph_only_same_relation_replacement' in reasons))
    assert len(cases) == len({c['input'] for c in cases}) == len(used) == 3000
    (HERE / 'factual.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cases))
    (HERE / 'corrections.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in changes))
    sources = {p.name: digest(p) for p in (ROOT / 'additional_files/src/chatbot').glob('*.py')}
    manifest = dict(timestamp=datetime.now(timezone.utc).isoformat(), seed=SEED, cases=3000,
                    original_sha256=digest(ORIGINAL), factual_sha256=digest(HERE / 'factual.jsonl'),
                    corrections_sha256=digest(HERE / 'corrections.jsonl'), graph_sha256=digest(GRAPH),
                    source_hashes=sources, build_script_sha256=digest(Path(__file__)),
                    replaced_records=sum(c['replacement'] for c in changes),
                    correction_counts=dict(Counter(reason for c in changes for reason in c['reasons'])),
                    relation_counts=dict(Counter(c['relation'] for c in cases)),
                    note='Corrected graph-grounded coverage suite, not a production sample. Original relation counts retained; graph-only replacements recorded. No agent imports or inference during construction.')
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == '__main__':
    main()
