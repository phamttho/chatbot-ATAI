"""Local graph, lexical candidate retrieval, and a bounded SPARQL query surface."""
from collections import defaultdict
from difflib import get_close_matches
import re
from pathlib import Path
import pyoxigraph as ox

PREFIXES = {'wd':'http://www.wikidata.org/entity/', 'wdt':'http://www.wikidata.org/prop/direct/',
            'rdfs':'http://www.w3.org/2000/01/rdf-schema#', 'xsd':'http://www.w3.org/2001/XMLSchema#'}


def normalize(text):
    return ' '.join(re.findall(r"\w+", text.casefold()))


class GraphStore:
    def __init__(self, path):
        self.store = ox.Store()
        path = Path(path)
        fmt = ox.RdfFormat.N_TRIPLES if path.suffix == '.nt' else ox.RdfFormat.TURTLE
        print(f'Loading graph: {path}', flush=True)
        self.store.load(path=path, format=fmt)
        self.labels = {}
        self.entities = defaultdict(list)
        self.properties = {}
        for row in self.store.query('SELECT ?s ?label WHERE { ?s rdfs:label ?label }', prefixes=PREFIXES):
            uri, label = row['s'].value, row['label'].value
            self.labels.setdefault(uri, label)
            if uri.startswith(PREFIXES['wd']):
                self.entities[normalize(label)].append(uri)
            elif uri.startswith(PREFIXES['wdt']):
                self.properties[uri.rsplit('/', 1)[-1]] = label
        print(f'Loaded {len(self.store):,} triples, {len(self.entities):,} labels, {len(self.properties)} properties', flush=True)

    def candidates(self, question):
        words = normalize(question).split()
        matches = []
        for size in range(min(12, len(words)), 0, -1):
            for i in range(len(words)-size+1):
                span = ' '.join(words[i:i+size])
                if span in self.entities and span not in {'who', 'what', 'which', 'when', 'where', 'how', 'the', 'a', 'an', 'is', 'was', 'of', 'by', 'for', 'movie', 'film', 'me', 'i', 'you', 'and', 'in', 'on'}:
                    for uri in self.entities[span]:
                        priority = int(self.labels[uri] in question and not question.startswith(self.labels[uri]+' '))
                        matches.append((size + priority * 20, uri))
        # Fuzzy lookup is confined to explicitly quoted mentions; no full question fuzzy matching.
        for mention in re.findall(r'''["“‘']([^"”’']{3,100})["”’']''', question):
            key = normalize(mention)
            if key not in self.entities:
                for match in get_close_matches(key, self.entities, n=2, cutoff=.86):
                    matches.extend((len(match.split()), uri) for uri in self.entities[match])
        output, seen = [], set()
        scores = {}
        for score, uri in sorted(matches, key=lambda item: -item[0]):
            if uri not in seen:
                seen.add(uri)
                scores[uri.rsplit('/', 1)[-1]] = score
                outgoing = set()
                incoming = set()
                node = ox.NamedNode(uri)
                for quad in self.store.quads_for_pattern(node, None, None):
                    if quad.predicate.value.startswith(PREFIXES['wdt']):
                        outgoing.add(quad.predicate.value.rsplit('/',1)[-1])
                for quad in self.store.quads_for_pattern(None, None, node):
                    if quad.predicate.value.startswith(PREFIXES['wdt']):
                        incoming.add(quad.predicate.value.rsplit('/',1)[-1])
                output.append(dict(id=uri.rsplit('/',1)[-1], label=self.labels[uri], outgoing=sorted(outgoing), incoming=sorted(incoming)))
            if len(output) == 12:
                break
        return sorted(output, key=lambda c: (-scores[c['id']], -len(c['outgoing'])))[:6]

    @staticmethod
    def expand_query(query):
        return '\n'.join(f'PREFIX {name}: <{uri}>' for name, uri in PREFIXES.items()) + '\n' + query

    def execute(self, query, candidates):
        """Accept only the documented one-edge SELECT grammar plus earliest/latest.

        A small grammar prevents SERVICE/network access, updates, unbounded joins,
        and arbitrary user/model SPARQL. Model still chooses entity, property,
        direction and ordering; there is no natural-language rule interpreter.
        """
        pattern = r'SELECT DISTINCT \?answer WHERE \{\s*(wd:Q\d+|\?answer)\s+wdt:(P\d+)\s+(wd:Q\d+|\?answer)\s*\.\s*(?:\?answer wdt:P577 \?date\s*\.\s*)?\}(?: ORDER BY (ASC|DESC)\(\?date\) LIMIT 1)?'
        match = re.fullmatch(pattern, query.strip())
        if not match:
            raise ValueError('Query must use the supplied single-hop SELECT template')
        head, prop, tail, order = match.groups()
        if (head == '?answer') == (tail == '?answer'):
            raise ValueError('Exactly one end of the triple must be ?answer')
        entity = tail if head == '?answer' else head
        allowed = {c['id'] for c in candidates}
        if entity[3:] not in allowed or prop not in self.properties:
            raise ValueError('Entity or property is not grounded in the graph context')
        selected = next(c for c in candidates if c['id'] == entity[3:])
        direction = 'incoming' if head == '?answer' else 'outgoing'
        if prop not in selected[direction]:
            raise ValueError(f'{prop} is unavailable in the {direction} edges of {entity}; select the matching candidate')
        if ('?date' in query) != bool(order) or (order and head != '?answer'):
            raise ValueError('Date ordering is only valid for inverse movie lookups')
        results = self.store.query(query, prefixes=PREFIXES)
        answers, values = [], []
        for row in results:
            node = row['answer']
            if isinstance(node, ox.NamedNode):
                label = self.labels.get(node.value)
                if label is None:
                    # Do not turn an opaque ID into a purported natural-language fact.
                    raise ValueError(f'Missing graph label for {node.value}')
                value = node.value
            else:
                value = node.value
                label = value
                if node.datatype.value in {PREFIXES['xsd']+'dateTime', PREFIXES['xsd']+'date'}:
                    label = value.split('T')[0]
            values.append(value)
            answers.append(label)
        return sorted(set(answers)), sorted(set(values))
