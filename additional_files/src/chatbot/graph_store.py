"""Local graph, lexical candidate retrieval, and a bounded SPARQL query surface."""
from collections import defaultdict, OrderedDict
from difflib import get_close_matches
from datetime import date
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pyoxigraph as ox

PREFIXES = {'wd':'http://www.wikidata.org/entity/', 'wdt':'http://www.wikidata.org/prop/direct/',
            'atai':'http://ddis.ch/atai/', 'rdfs':'http://www.w3.org/2000/01/rdf-schema#', 'xsd':'http://www.w3.org/2001/XMLSchema#'}


def normalize(text):
    return ' '.join(re.findall(r"\w+", text.casefold()))


class ClarificationNeeded(ValueError):
    """More than one plausible graph entity has the requested relation."""


class MissingFact(ValueError):
    """A known entity has no recorded value for the requested property."""


class UnsupportedQuery(ValueError):
    """The requested operation is outside the supported graph query surface."""


def quoted_mentions(text):
    # Quotation styles must be paired: an apostrophe inside a double-quoted
    # title is part of its name, and possessives are not closing quotes.
    pattern = r""""([^"\n]+)"|“([^”\n]+)”|‘([^’\n]+)’|(?<!\w)'(.+?)'(?!\w)"""
    return [next(group for group in groups if group) for groups in re.findall(pattern, text)]


def title_key(text):
    return re.sub(r'^(?:the|an|a) ', '', normalize(text))


FILM_TYPES = {'Q11424','Q202866','Q24862','Q506240','Q17517379','Q226730'}


class GraphStore:
    def __init__(self, path):
        self.store = ox.Store()
        self._approved_selections = OrderedDict()
        path = Path(path)
        fmt = ox.RdfFormat.N_TRIPLES if path.suffix == '.nt' else ox.RdfFormat.TURTLE
        print(f'Loading graph: {path}', flush=True)
        self.store.load(path=path, format=fmt)
        self.labels = {}
        self.entities = defaultdict(list)
        self.properties = {'tag': 'user tags', 'rating': 'user rating (0 to 10)'}
        self.aliases = defaultdict(set)
        for row in self.store.query('SELECT ?s ?label WHERE { ?s rdfs:label ?label }', prefixes=PREFIXES):
            uri, label = row['s'].value, row['label'].value
            self.labels.setdefault(uri, label)
            if uri.startswith(PREFIXES['wd']):
                self.entities[normalize(label)].append(uri)
                self.aliases[uri].add(label)
            elif uri.startswith(PREFIXES['wdt']):
                self.properties[uri.rsplit('/', 1)[-1]] = label
        # Graph aliases and article-free titles are retrieval keys, not invented facts.
        for predicate in ['http://www.w3.org/2004/02/skos/core#altLabel',
                          'http://schema.org/alternateName', PREFIXES['wdt']+'P1476']:
            for quad in self.store.quads_for_pattern(None, ox.NamedNode(predicate), None):
                if quad.subject.value in self.labels and isinstance(quad.object, ox.Literal):
                    self.aliases[quad.subject.value].add(quad.object.value)
        for uri, names in self.aliases.items():
            for name in names:
                for key in {normalize(name), title_key(name)}:
                    if key and uri not in self.entities[key]:
                        self.entities[key].append(uri)
        print(f'Loaded {len(self.store):,} triples, {len(self.entities):,} labels, {len(self.properties)} properties', flush=True)

    def candidates(self, question):
        words = normalize(question).split()
        quoted = quoted_mentions(question)
        quoted_keys = {normalize(name) for name in quoted}
        matches, matched_names = {}, {}
        stop = {'who','what','which','when','where','how','the','a','an','is','was',
                'of','by','for','movie','film','me','i','you','and','in','on'}
        for size in range(min(12, len(words)), 0, -1):
            for i in range(len(words)-size+1):
                span = ' '.join(words[i:i+size])
                # Decimal thresholds are not references to movies named "9".
                if (span in stop or span.isdecimal()) and span not in quoted_keys:
                    # A literal punctuation-bearing title such as &ME remains
                    # a name even when its normalized key is a stop word.
                    explicit_title = any(
                        re.search(r'[^\w\s]', alias)
                        and re.search(r'(?<!\w)' + re.escape(alias) + r'(?!\w)', question, re.I)
                        for uri in self.entities.get(span, []) for alias in self.aliases[uri])
                    if not explicit_title:
                        continue
                for uri in self.entities.get(span, []):
                    label = self.labels[uri]
                    literal = bool(re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',question,re.I))
                    exact = 4 + min(2,len(re.findall(r'[^\w\s]',label))) if normalize(label)==span and literal else (2 if any(normalize(a)==span for a in self.aliases[uri]) else 0)
                    score = size * 10 + exact + (100 if span in quoted_keys else 0)
                    if score > matches.get(uri, -1):
                        matches[uri], matched_names[uri] = score, span
        # Fuzzy matches only for quoted mentions or a bounded trailing name.
        mentions = quoted or re.findall(r'\b(?:of|for|on|by)\s+(.+?)[?.!]*$', question, re.I)
        for mention in mentions:
            key = normalize(mention)
            if len(key) >= 4 and key not in self.entities:
                for match in get_close_matches(key, self.entities, n=2, cutoff=.86):
                    for uri in self.entities[match]:
                        score = len(match.split())*10-1
                        if score > matches.get(uri,-1):
                            matches[uri], matched_names[uri] = score, key
        output = []
        for uri, score in sorted(matches.items(), key=lambda item: (-item[1], item[0]))[:12]:
            outgoing, incoming, dates, types = set(), set(), [], set()
            node = ox.NamedNode(uri)
            for quad in self.store.quads_for_pattern(node, None, None):
                prop = self.property_key(quad.predicate.value)
                if prop:
                    outgoing.add(prop)
                if prop == 'P31' and isinstance(quad.object, ox.NamedNode):
                    types.add(quad.object.value.rsplit('/',1)[-1])
                if prop == 'P577' and isinstance(quad.object, ox.Literal):
                    dates.append(quad.object.value[:10])
            for quad in self.store.quads_for_pattern(None, None, node):
                prop = self.property_key(quad.predicate.value)
                if prop:
                    incoming.add(prop)
            if {d[:4] for d in dates} & set(re.findall(r'\b(?:18|19|20)\d{2}\b', question)):
                score += 5
            output.append(dict(id=uri.rsplit('/',1)[-1], label=self.labels[uri],
                               outgoing=sorted(outgoing), incoming=sorted(incoming),
                               match_score=score, matched_name=matched_names[uri], is_film=bool(types & FILM_TYPES), release_dates=sorted(set(dates))[:3]))
        return sorted(output, key=lambda c: (-c['match_score'], -len(c['outgoing']), c['id']))[:6]

    @staticmethod
    def property_key(uri):
        if uri.startswith(PREFIXES['wdt']):
            return uri.rsplit('/', 1)[-1]
        if uri in {PREFIXES['atai']+'tag', PREFIXES['atai']+'rating'}:
            return uri.rsplit('/', 1)[-1]
        return None

    def compile_plan(self, plan, candidates):
        """Turn a small validated data object into SPARQL; never execute model syntax."""
        if not isinstance(plan, dict):
            raise ValueError('Query plan must be an object')
        if plan.get('operation') == 'select':
            return self._compile_selection(plan, candidates)
        allowed = {'operation','entity','property','direction','order','comparison','value'}
        if plan.get('operation') in {'clarify', 'unsupported'}:
            # Some models add explanatory metadata to non-executing plans.
            # Ignore it and use our fixed response; never execute or display it.
            allowed.add('reason')
        if set(plan)-allowed:
            raise ValueError('Unknown query plan fields')
        operation = plan.get('operation')
        if operation == 'clarify':
            if plan.get('reason') == 'multiple_questions':
                raise ClarificationNeeded('Please send these as separate questions so I can answer each accurately.')
            raise ClarificationNeeded('Please provide the full film title and release year.')
        if operation == 'unsupported':
            raise UnsupportedQuery('That operation is not supported by this movie graph assistant.')
        if operation not in {'lookup','count','filter'}:
            raise ValueError('Unknown query operation')
        prop = plan.get('property')
        if not isinstance(prop, str) or prop not in self.properties:
            raise UnsupportedQuery('The requested property is not available in the graph context.')
        predicate = ('atai:' if prop in {'tag','rating'} else 'wdt:')+prop
        if operation == 'filter':
            if prop == 'P577' and (plan.get('order') is not None or (
                    isinstance(plan.get('value'), (str, int)) and re.fullmatch(r'\d{4}', str(plan['value'])))):
                if any(plan.get(k) is not None for k in ['entity', 'direction']):
                    raise ValueError('Global release-date filters cannot select a named entity')
                return self._compile_selection(dict(operation='select', result=plan.get('order') or 'list', filters=[
                    dict(property=prop, comparison=plan.get('comparison'), value=plan['value'])]), candidates)
            if prop not in {'rating', 'P577'} or any(plan.get(k) is not None for k in ['entity','direction','order']):
                raise UnsupportedQuery('Filtering supports recorded user ratings and movie release dates without a named entity.')
            comparisons = {'gte':'>=', 'gt':'>', 'lte':'<=', 'lt':'<', 'eq':'=', 'ne':'!='}
            comparison = plan.get('comparison')
            if not isinstance(comparison,str) or comparison not in comparisons:
                raise ValueError('Unknown comparison')
            value = plan.get('value')
            if prop == 'P577':
                return self._date_filter_query(comparisons[comparison], value)
            if isinstance(value, bool) or not isinstance(value, (str,int,float)) or len(str(value))>24:
                raise ValueError('Invalid numeric threshold')
            try:
                number = Decimal(str(value))
            except InvalidOperation as exc:
                raise ValueError('Invalid numeric threshold') from exc
            if (not number.is_finite() or not 0 <= number <= 10
                    or number.as_tuple().exponent < -18 or len(number.as_tuple().digits) > 20):
                raise ValueError('User rating threshold must be between 0 and 10')
            # Requiring the rating triple excludes movies with unknown ratings.
            return f'SELECT DISTINCT ?answer WHERE {{ ?answer atai:rating ?rating . FILTER(?rating {comparisons[comparison]} {number:f}) }}'
        if any(plan.get(k) is not None for k in ['comparison','value']):
            raise ValueError('Comparisons require a filter operation')
        if not candidates:
            raise MissingFact("I could not find a matching film or person in the knowledge graph. Please check the name or provide the film's release year.")
        entity = plan.get('entity')
        if not isinstance(entity,str) or not re.fullmatch(r'Q\d+',entity):
            raise ValueError('Expected a retrieved entity ID')
        direction = plan.get('direction','outgoing')
        if direction not in {'outgoing','incoming'}:
            raise ValueError('Invalid relation direction')
        selected = next((c for c in candidates if c['id']==entity), None)
        if selected is None:
            raise ValueError('Entity ID was not retrieved from the graph')
        opposite = 'incoming' if direction=='outgoing' else 'outgoing'
        if prop not in selected[direction] and prop in selected[opposite]:
            # A relation present in only one direction has a unique graph-supported orientation.
            direction = opposite
        available = [c for c in candidates if prop in c[direction] or operation == 'count']
        if not available:
            raise MissingFact('The requested fact is not recorded for the retrieved entities.')
        best_score = max(c.get('match_score',0) for c in available)
        best = [c for c in available if c.get('match_score',0)==best_score]
        films = [c for c in best if c.get('is_film')]
        if films and direction=='outgoing':
            best = films
        if len(best)>1:
            # A role phrase may also be a title (e.g. 'the producers'). Only
            # alternatives matching the SAME mention make the selected name ambiguous.
            mention = selected.get('matched_name',title_key(selected['label']))
            best = [c for c in best if c.get('matched_name',title_key(c['label']))==mention]
        if len(best)>1:
            names = '; '.join(c['label']+(' ('+', '.join(c.get('release_dates',[]))+')' if c.get('release_dates') else '')+' ['+c['id']+']' for c in best)
            raise ClarificationNeeded('Which film or person do you mean? '+names)
        if not best or entity != best[0]['id']:
            raise ValueError('Selected entity does not match the strongest retrieved name with this relation')
        order = plan.get('order')
        if order not in {None,'earliest','latest'}:
            raise ValueError('Invalid date order')
        if operation == 'count' and order is not None:
            raise ValueError('Count cannot use date ordering')
        head, tail = ('?answer','wd:'+entity) if direction=='incoming' else ('wd:'+entity,'?answer')
        if operation == 'count':
            return f'SELECT (COUNT(DISTINCT ?answer) AS ?count) WHERE {{ {head} {predicate} {tail} . }}'
        query = f'SELECT DISTINCT ?answer WHERE {{ {head} {predicate} {tail} .'
        if order:
            if direction != 'incoming':
                raise ValueError('Date ordering requires an incoming movie lookup')
            query += ' ?answer wdt:P577 ?date .'
        query += ' }'
        if order:
            query += ' ORDER BY '+('ASC' if order=='earliest' else 'DESC')+'(?date) LIMIT 1'
        return query

    @staticmethod
    def _rating_number(value):
        if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 24:
            raise ValueError('Invalid rating threshold')
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError('Invalid rating threshold') from exc
        if (not number.is_finite() or not 0 <= number <= 10
                or number.as_tuple().exponent < -18 or len(number.as_tuple().digits) > 20):
            raise ValueError('Rating threshold must be between 0 and 10')
        return format(number, 'f')

    @staticmethod
    def _calendar_condition(variable, comparison, value):
        operators = {'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<=', 'eq': '=', 'ne': '!='}
        if not isinstance(comparison, str) or comparison not in operators:
            raise ValueError('Unknown date comparison')
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ClarificationNeeded('Please provide a valid four-digit release year or YYYY-MM-DD date.')
        value = str(value)
        def literal(day):
            return '"' + day + 'T00:00:00"^^xsd:dateTime'
        if re.fullmatch(r'\d{4}', value):
            if not 1 <= int(value) <= 9999:
                raise ClarificationNeeded('Please provide a release year between 0001 and 9999.')
            first, last = literal(value + '-01-01'), literal(value + '-12-31')
            return {
                'gt': f'{variable} > {last}', 'gte': f'{variable} >= {first}',
                'lt': f'{variable} < {first}', 'lte': f'{variable} <= {last}',
                'eq': f'({variable} >= {first} && {variable} <= {last})',
                'ne': f'({variable} < {first} || {variable} > {last})',
            }[comparison]
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ClarificationNeeded('Please provide a valid four-digit release year or YYYY-MM-DD date.')
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ClarificationNeeded('Please provide a valid calendar date in YYYY-MM-DD form.') from exc
        return f'{variable} {operators[comparison]} {literal(value)}'

    def _compile_selection(self, plan, candidates):
        """Compose a bounded movie selection, then aggregate/order the same set."""
        if set(plan) - {'operation', 'filters', 'result'}:
            raise ValueError('Unknown movie-selection fields')
        result = plan.get('result', 'list')
        if not isinstance(result, str) or result not in {'list', 'count', 'earliest', 'latest'}:
            raise ValueError('Unknown movie-selection result')
        filters = plan.get('filters', [])
        if not isinstance(filters, list) or len(filters) > 4:
            raise ValueError('Expected at most four movie-selection filters')
        film_types = ' '.join('wd:' + kind for kind in sorted(FILM_TYPES))
        body = f'?answer wdt:P31 ?film_type . VALUES ?film_type {{ {film_types} }} '
        needs_date = result in {'earliest', 'latest'} or any(
            isinstance(f, dict) and f.get('property') == 'P577' for f in filters)
        if needs_date:
            body += ('?answer wdt:P577 ?release_date . '
                     'BIND(xsd:dateTime(CONCAT(SUBSTR(STR(?release_date),1,10),"T00:00:00")) AS ?day) '
                     'FILTER(BOUND(?day)) ')
        has_rating = False
        operators = {'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<=', 'eq': '=', 'ne': '!='}
        for index, constraint in enumerate(filters):
            if not isinstance(constraint, dict):
                raise ValueError('Movie-selection filters must be objects')
            prop, comparison = constraint.get('property'), constraint.get('comparison')
            if not isinstance(prop, str) or prop not in self.properties:
                raise UnsupportedQuery('The requested filter property is not in the graph.')
            if prop in {'P577', 'rating'}:
                if set(constraint) != {'property', 'comparison', 'value'}:
                    raise ValueError('Date/rating filters require only property, comparison and value')
                if prop == 'P577':
                    body += f'FILTER({self._calendar_condition("?day", comparison, constraint["value"])}) '
                else:
                    if not isinstance(comparison, str) or comparison not in operators:
                        raise ValueError('Unknown rating comparison')
                    if not has_rating:
                        body += '?answer atai:rating ?rating . '
                        has_rating = True
                    number = self._rating_number(constraint['value'])
                    body += f'FILTER(?rating {operators[comparison]} {number}) '
                continue
            if (set(constraint) != {'property', 'comparison', 'entity'}
                    or not isinstance(comparison, str) or comparison not in {'eq', 'ne'} or not re.fullmatch(r'P\d+', prop)):
                raise ValueError('Entity filters require a graph property, eq/ne comparison and retrieved entity')
            entity = constraint['entity']
            # Reuse the same retrieval/ranking checks as ordinary inverse lookups.
            inverse = self.compile_plan(dict(operation='lookup', property=prop, entity=entity,
                                             direction='incoming'), candidates)
            if not inverse.startswith('SELECT DISTINCT ?answer WHERE { ?answer '):
                raise ClarificationNeeded('Please identify the person or entity associated with the requested movie relation.')
            if comparison == 'eq':
                body += f'?answer wdt:{prop} wd:{entity} . '
            else:
                # Missing director data is not evidence of a different director.
                # NOT EXISTS also excludes a co-directed film containing this person.
                body += (f'?answer wdt:{prop} ?known_{index} . '
                         f'FILTER NOT EXISTS {{ ?answer wdt:{prop} wd:{entity} . }} ')
        if result == 'count':
            query = f'SELECT (COUNT(DISTINCT ?answer) AS ?count) WHERE {{ {body}}}'
        elif result in {'earliest', 'latest'}:
            aggregate = 'MIN' if result == 'earliest' else 'MAX'
            # Return all tied movies rather than silently choosing an arbitrary one.
            query = (f'SELECT DISTINCT ?answer WHERE {{ {body}'
                     f'{{ SELECT ({aggregate}(?day) AS ?extreme) WHERE {{ {body}}} }} '
                     'FILTER(?day = ?extreme) }')
        else:
            query = f'SELECT DISTINCT ?answer WHERE {{ {body}}}'
        self._approved_selections[query] = result
        self._approved_selections.move_to_end(query)
        if len(self._approved_selections) > 64:
            self._approved_selections.popitem(last=False)
        return query

    @staticmethod
    def _date_filter_query(operator, value):
        if operator not in {'>=', '>', '<=', '<', '=', '!='}:
            raise ValueError('Invalid date comparison')
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('Release date must use YYYY-MM-DD')
        date.fromisoformat(value)  # Reject impossible calendar dates before SPARQL.
        film_types = ' '.join('wd:' + kind for kind in sorted(FILM_TYPES))
        # Compare calendar dates consistently across xsd:date and xsd:dateTime.
        # Requiring a recorded film type excludes people, books and other works.
        return (f'SELECT DISTINCT ?answer WHERE {{ ?answer wdt:P31 ?film_type . '
                f'VALUES ?film_type {{ {film_types} }} ?answer wdt:P577 ?release_date . '
                f'FILTER(xsd:dateTime(CONCAT(SUBSTR(STR(?release_date),1,10),"T00:00:00")) '
                f'{operator} "{value}T00:00:00"^^xsd:dateTime) }}')

    @staticmethod
    def expand_query(query):
        return '\n'.join(f'PREFIX {name}: <{uri}>' for name, uri in PREFIXES.items()) + '\n' + query

    def execute(self, query, candidates):
        """Accept only the documented one-edge SELECT grammar plus earliest/latest.

        A small grammar prevents SERVICE/network access, updates, unbounded joins,
        and arbitrary user/model SPARQL. Model still chooses entity, property,
        direction and ordering; there is no natural-language rule interpreter.
        """
        if query in self._approved_selections:
            rows = self.store.query(query, prefixes=PREFIXES)
            if self._approved_selections[query] == 'count':
                count = next(iter(rows))['count'].value
                return [count], [count]
            return self._answers(rows)
        date_match = re.search(r'FILTER\(xsd:dateTime\(CONCAT\(SUBSTR\(STR\(\?release_date\),1,10\),"T00:00:00"\)\) (>=|>|<=|<|=|!=) "(\d{4}-\d{2}-\d{2})T00:00:00"\^\^xsd:dateTime\) \}$', query)
        if date_match and query == self._date_filter_query(date_match[1], date_match[2]):
            return self._answers(self.store.query(query, prefixes=PREFIXES))
        filter_match = re.fullmatch(r'SELECT DISTINCT \?answer WHERE \{ \?answer atai:rating \?rating \. FILTER\(\?rating (>=|>|<=|<|=|!=) ([0-9]+(?:\.[0-9]+)?)\) \}', query)
        if filter_match:
            threshold = Decimal(filter_match[2])
            if not 0 <= threshold <= 10:
                raise ValueError('Rating threshold out of range')
            return self._answers(self.store.query(query, prefixes=PREFIXES))
        count_match = re.fullmatch(r'SELECT \(COUNT\(DISTINCT \?answer\) AS \?count\) WHERE \{ (wd:Q\d+|\?answer) (wdt:P\d+|atai:(?:tag|rating)) (wd:Q\d+|\?answer) \. \}', query)
        if count_match:
            head, predicate, tail = count_match.groups()
            self._validate_edge(head, predicate.split(':')[1], tail, candidates, allow_missing=True)
            row = next(iter(self.store.query(query, prefixes=PREFIXES)))
            return [row['count'].value], [row['count'].value]
        pattern = r'SELECT DISTINCT \?answer WHERE \{\s*(wd:Q\d+|\?answer)\s+(?:wdt:(P\d+)|atai:(tag|rating))\s+(wd:Q\d+|\?answer)\s*\.\s*(?:\?answer wdt:P577 \?date\s*\.\s*)?\}(?: ORDER BY (ASC|DESC)\(\?date\) LIMIT 1)?'
        match = re.fullmatch(pattern, query.strip())
        if not match:
            raise ValueError('Query must use the supplied single-hop SELECT template')
        head, wikidata_prop, custom_prop, tail, order = match.groups()
        prop = wikidata_prop or custom_prop
        self._validate_edge(head, prop, tail, candidates)
        if ('?date' in query) != bool(order) or (order and head != '?answer'):
            raise ValueError('Date ordering is only valid for inverse movie lookups')
        results = self.store.query(query, prefixes=PREFIXES)
        return self._answers(results)

    def _validate_edge(self, head, prop, tail, candidates, allow_missing=False):
        if (head == '?answer') == (tail == '?answer'):
            raise ValueError('Exactly one end of the triple must be ?answer')
        entity = tail if head == '?answer' else head
        allowed = {c['id'] for c in candidates}
        if entity[3:] not in allowed or prop not in self.properties:
            raise ValueError('Entity or property is not grounded in the graph context')
        selected = next(c for c in candidates if c['id'] == entity[3:])
        direction = 'incoming' if head == '?answer' else 'outgoing'
        if prop not in selected[direction] and not allow_missing:
            raise ValueError(f'{prop} is unavailable in the {direction} edges of {entity}; select the matching candidate')

    def _answers(self, results):
        answers, values = [], []
        for row in results:
            node = row['answer']
            if isinstance(node, ox.NamedNode):
                label = self.labels.get(node.value)
                if label is None:
                    # Preserve real records without inventing a missing title/name.
                    label = f'Unlabelled graph entity ({node.value.rsplit("/", 1)[-1]})'
                value = node.value
            else:
                value = node.value
                label = value
                if node.datatype.value in {PREFIXES['xsd']+'dateTime', PREFIXES['xsd']+'date'}:
                    label = value.split('T')[0]
            values.append(value)
            answers.append(label)
        return sorted(set(answers)), sorted(set(values))
