import re
import os
from difflib import SequenceMatcher

from rdflib import Literal, URIRef
from rdflib.namespace import RDFS

from knowledge_graph import SPARQLAgent


WDT = "http://www.wikidata.org/prop/direct/"

PREFIXES = """\
PREFIX ddis: <http://ddis.ch/atai/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


# Extra paraphrases for the relations that are most likely to appear in the
# movie questions used by the course. Property labels from the graph are also
# indexed automatically, so this table mainly covers normal English phrasing.
PROPERTY_ALIASES = {
    "P57": [
        "director", "directed by", "directed", "direct", "who directed",
    ],
    "P58": [
        "screenwriter", "screenplay", "wrote the screenplay", "written by",
        "writer", "writers", "screenplay by",
    ],
    "P86": [
        "composer", "composed by", "music by", "score by", "film score",
        "soundtrack composer",
    ],
    "P136": [
        "genre", "genres", "type of film", "type of movie", "kind of film",
        "kind of movie",
    ],
    "P161": [
        "cast member", "cast members", "cast", "starring", "stars",
        "actor", "actors", "actress", "actresses",
    ],
    "P162": [
        "producer", "producers", "produced by",
    ],
    "P166": [
        "award received", "awards received", "award", "awards", "won",
        "received", "prize", "prizes",
    ],
    "P495": [
        "country of origin", "countries of origin", "origin country",
        "origin countries", "which country", "what country", "from which country",
    ],
    "P577": [
        "publication date", "release date", "released", "release", "came out",
        "come out", "premiered", "premiere date", "first released",
    ],
    "P364": [
        "original language", "language of the film", "language of the movie",
        "language",
    ],
    "P344": [
        "director of photography", "cinematographer", "cinematography by",
    ],
    "P1040": [
        "film editor", "edited by", "editor",
    ],
    "P2515": [
        "costume designer", "costume designers", "costumes by",
        "designed the costumes",
    ],
    "P2554": [
        "production designer", "production design",
    ],
    "P272": [
        "production company", "production companies",
    ],
    "P750": [
        "distributed by", "distributor", "distributors",
    ],
    "P915": [
        "filming location", "filming locations", "filmed in", "shot in",
        "where was it filmed", "where was the movie filmed",
    ],
    "P840": [
        "narrative location", "set in", "takes place in", "take place in",
        "story set in",
    ],
    "P144": [
        "based on", "source material",
    ],
    "P725": [
        "voice actor", "voice actors", "voiced by",
    ],
    "P2438": [
        "narrator", "narrated by",
    ],
    "P1431": [
        "executive producer", "executive producers",
    ],
    "P3092": [
        "film crew member", "film crew", "crew member",
    ],
    "P3174": [
        "art director", "art directors",
    ],
    "P3275": [
        "storyboard artist", "storyboard artists",
    ],
    "P5028": [
        "sound designer", "sound designers", "sound design",
    ],
    "P6942": [
        "animator", "animators",
    ],
    "P1809": [
        "choreographer", "choreography",
    ],
    "P2142": [
        "box office", "box office revenue", "gross", "revenue",
    ],
    "P345": [
        "imdb id", "imdb identifier", "imdb",
    ],
    "P437": [
        "distribution format", "format",
    ],
    "P462": [
        "color", "colour",
    ],
    "P2408": [
        "set in period", "time period", "period set in",
    ],
    "P942": [
        "theme music", "theme song",
    ],
    "P674": [
        "characters", "character",
    ],
    "P921": [
        "main subject", "subject",
    ],
    "P31": [
        "instance of", "type",
    ],
}


GENERIC_ENTITY_WORDS = {
    "movie", "movies", "film", "films", "director", "directors", "actor",
    "actors", "actress", "actresses", "composer", "country", "countries",
    "genre", "genres", "award", "awards", "producer", "producers", "writer",
    "writers", "screenwriter", "screenwriters", "editor", "editors", "language",
}

QUESTION_WORDS = {
    "a", "an", "the", "who", "what", "which", "when", "where", "why",
    "how", "many", "much", "does", "do", "did", "is", "are", "was",
    "were", "has", "have", "had", "this", "that", "movie", "movies",
    "film", "films", "of", "for", "by", "in", "on", "from", "to",
    "with", "without", "origin", "country", "countries", "date", "dates",
    "released", "release", "before", "after", "earlier", "later", "come",
    "out", "earliest", "oldest", "latest", "newest", "recent", "recently",
    "directed", "written", "produced", "received", "listed",
}


class FactualQAAgent:
    """Stage 2 factual question answering over the course knowledge graph.

    The agent keeps Stage 1 support: if a message is already SPARQL it is passed
    directly to SPARQLAgent. Otherwise the natural-language question is mapped to
    a single-hop SPARQL query and answered from the graph.
    """

    def __init__(self, graph_path):
        self.sparql_agent = SPARQLAgent(graph_path)
        self.graph = self.sparql_agent.graph
        self.known_labels = set()
        self.label_text_by_normalized = {}
        self.labels_by_word_count = {}
        self.label_subjects = {}
        self.preferred_label_by_subject = {}
        self.dynamic_relation_aliases = {}
        self._build_indexes()

    @staticmethod
    def _normalize(text):
        text = str(text).casefold()
        text = text.replace("’", "'").replace("‘", "'")
        text = text.replace("“", '"').replace("”", '"')
        text = re.sub(r"[^\w\s'-]", " ", text, flags=re.UNICODE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _is_sparql(text):
        if not isinstance(text, str):
            return False
        meaningful = []
        for line in text.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            meaningful.append(line)
        if not meaningful:
            return False
        first = meaningful[0].upper()
        return first.startswith(("PREFIX", "BASE", "SELECT", "ASK", "CONSTRUCT", "DESCRIBE"))

    def _build_indexes(self):
        """Index entity labels and property labels already contained in graph.nt."""
        property_count = 0
        for subject, label in self.graph.subject_objects(RDFS.label):
            label_text = str(label).strip()
            if label_text:
                normalized_label = self._normalize(label_text)
                self.known_labels.add(normalized_label)
                self.label_text_by_normalized.setdefault(normalized_label, label_text)
                self.labels_by_word_count.setdefault(
                    len(normalized_label.split()), {}
                )[normalized_label] = label_text
                self.label_subjects.setdefault(normalized_label, set()).add(subject)
                self.preferred_label_by_subject.setdefault(subject, label_text)

            subject_text = str(subject)
            if subject_text.startswith(WDT):
                pid = subject_text[len(WDT):]
                normalized_label = self._normalize(label_text)
                if normalized_label:
                    self.dynamic_relation_aliases.setdefault(pid, set()).add(normalized_label)
                    property_count += 1

        print(
            f"Indexed {len(self.known_labels):,} labels and "
            f"{len(self.dynamic_relation_aliases):,} relation properties."
        )

    @staticmethod
    def _strip_instruction(question):
        text = question.strip()
        # Website/test prompts are sometimes pasted with their list number.
        text = re.sub(r"^\s*(?:\d+[.)]|[-*])\s*", "", text)
        patterns = [
            r"^please\s+answer\s+this\s+question\s+with\s+(?:a\s+)?factual\s+approach\s*:\s*",
            r"^please\s+answer\s+this\s+question\s*:\s*",
            r"^answer\s+this\s+question\s+with\s+(?:a\s+)?factual\s+approach\s*:\s*",
            r"^factual\s+approach\s*:\s*",
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        return text.strip()

    def _quoted_mentions(self, question):
        matches = []
        patterns = [
            r'"([^"\n]+)"',
            r"“([^”\n]+)”",
            r"‘([^’\n]+)’",
            r"'([^'\n]+)'",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, question):
                cleaned = match.strip()
                if cleaned and cleaned not in matches:
                    matches.append(cleaned)
        return matches

    def _extract_entity_mention(self, question):
        quoted = self._quoted_mentions(question)
        if quoted:
            # Prefer a quoted string that actually exists as a graph label.
            for mention in quoted:
                if self._normalize(mention) in self.known_labels:
                    return self.label_text_by_normalized.get(
                        self._normalize(mention), mention
                    )

            # Quotation marks are optional and typos are allowed. Resolve a
            # quoted near-match to the closest graph label.
            for mention in quoted:
                resolved = self._fuzzy_label_match(mention)
                if resolved:
                    return resolved
            return quoted[0]

        # Fallback for questions without quotes: test n-grams against labels from
        # the graph, preferring the longest matching label.
        tokens = re.findall(r"[\wÀ-ÖØ-öø-ÿ'’-]+", question, flags=re.UNICODE)
        best = None
        max_span = min(10, len(tokens))

        for span in range(max_span, 0, -1):
            for start in range(0, len(tokens) - span + 1):
                candidate = " ".join(tokens[start:start + span]).strip(" '-")
                normalized = self._normalize(candidate)
                if not normalized or self._is_non_entity_candidate(normalized):
                    continue
                if normalized in self.known_labels:
                    return self.label_text_by_normalized.get(normalized, candidate)

        # Handle small misspellings such as "Insde Out". The question scope
        # excludes vague descriptions, so fuzzy matching is only applied to
        # short text spans that resemble an actual graph label.
        for span in range(max_span, 0, -1):
            for start in range(0, len(tokens) - span + 1):
                candidate = " ".join(tokens[start:start + span]).strip(" '-")
                if self._is_non_entity_candidate(self._normalize(candidate)):
                    continue
                resolved = self._fuzzy_label_match(candidate)
                if resolved:
                    return resolved

        return best

    def _fuzzy_label_match(self, mention, threshold=0.78):
        """Return the closest graph label for a small typo, if unambiguous."""
        normalized = self._normalize(mention)
        if not normalized or self._is_non_entity_candidate(normalized):
            return None

        mention_words = normalized.split()
        candidates = []
        first_character = normalized[0]
        max_length_delta = max(3, int(len(normalized) * 0.25))
        for word_count in range(max(1, len(mention_words) - 1), len(mention_words) + 2):
            for label_normalized, label_text in self.labels_by_word_count.get(
                word_count, {}
            ).items():
                # Avoid comparing a typo against every graph label. Small
                # misspellings normally preserve the first character and have
                # a similar length; this keeps fuzzy matching responsive on
                # the full 123k-label graph.
                if not label_normalized:
                    continue
                if label_normalized[0] != first_character:
                    continue
                if abs(len(label_normalized) - len(normalized)) > max_length_delta:
                    continue
                score = SequenceMatcher(None, normalized, label_normalized).ratio()
                if score >= threshold:
                    candidates.append((score, label_text))

        candidates.sort(reverse=True)
        if not candidates:
            return None
        # Do not guess when two labels are effectively equally close.
        if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.015:
            return None
        return candidates[0][1]

    @staticmethod
    def _is_non_entity_candidate(normalized):
        words = normalized.split()
        return (
            not words
            or normalized in GENERIC_ENTITY_WORDS
            or any(word.isdigit() for word in words)
            or all(word in QUESTION_WORDS for word in words)
        )

    @staticmethod
    def _ngrams(text, max_words=5):
        tokens = text.split()
        grams = []
        for size in range(1, min(max_words, len(tokens)) + 1):
            for start in range(len(tokens) - size + 1):
                grams.append(" ".join(tokens[start:start + size]))
        return grams

    def _detect_relation(self, question, exclude=None):
        exclude = set(exclude or [])
        normalized_question = self._normalize(question)
        candidates = []

        # Hand-written paraphrases receive the highest priority.
        for pid, aliases in PROPERTY_ALIASES.items():
            if pid in exclude:
                continue
            for alias in aliases:
                normalized_alias = self._normalize(alias)
                if normalized_alias and normalized_alias in normalized_question:
                    candidates.append(
                        (1000 + len(normalized_alias.split()) * 20 + len(normalized_alias), pid, alias)
                    )

        # Also use the official relation labels present in graph.nt itself.
        for pid, aliases in self.dynamic_relation_aliases.items():
            if pid in exclude:
                continue
            for normalized_alias in aliases:
                if normalized_alias and normalized_alias in normalized_question:
                    candidates.append(
                        (500 + len(normalized_alias.split()) * 20 + len(normalized_alias), pid, normalized_alias)
                    )

        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]

        # Conservative fuzzy fallback for small wording variations/typos.
        grams = self._ngrams(normalized_question)
        best_score = 0.0
        best_pid = None

        alias_sources = {}
        for pid, aliases in PROPERTY_ALIASES.items():
            alias_sources.setdefault(pid, set()).update(self._normalize(x) for x in aliases)
        for pid, aliases in self.dynamic_relation_aliases.items():
            alias_sources.setdefault(pid, set()).update(aliases)

        for pid, aliases in alias_sources.items():
            if pid in exclude:
                continue
            for alias in aliases:
                if len(alias) < 4:
                    continue
                alias_words = len(alias.split())
                for gram in grams:
                    if abs(len(gram.split()) - alias_words) > 1:
                        continue
                    score = SequenceMatcher(None, alias, gram).ratio()
                    if score > best_score:
                        best_score = score
                        best_pid = pid

        return best_pid if best_score >= 0.86 else None

    def _infer_direction(self, question):
        q = self._normalize(question)
        # The answer is the subject of the relation for forms such as
        # "which movies did X direct?" and "films directed by X".
        head_patterns = (
            "which movie", "which movies", "which film", "which films",
            "what movie", "what movies", "what film", "what films",
            "name a movie", "name the movie", "name the movies",
            "how many movies", "how many films",
        )
        if q.startswith(head_patterns) or re.search(
            r"\b(movie|movies|film|films)\s+(?:that|which)?\s*(?:were|was)?\s*"
            r"(?:directed|written|produced|edited|made)\s+by\b",
            q,
        ):
            return "head"

        # In "who was X directed by?", X is the known subject and the
        # answer is the object of the relation.
        if re.search(r"\b(who|what person|which person)\b.*\bby\b", q):
            return "tail"

        return "tail"

    @staticmethod
    def _literal_n3(value):
        return Literal(value).n3()

    def _is_negated(self, question):
        q = self._normalize(question)
        return bool(re.search(r"\b(?:not|n't|never|without|no)\b", q))

    def _build_single_hop_query(
        self,
        mention,
        pid,
        direction,
        count=False,
        negated=False,
        filter_clause="",
        movie_question=False,
    ):
        label_literal = self._literal_n3(mention)
        property_ref = f"wdt:{pid}"

        if direction == "head" and not negated:
            triple = f"?answer {property_ref} ?known ."
        elif direction == "tail" and not negated:
            triple = f"?known {property_ref} ?answer ."
        elif direction == "head":
            triple = f"?answer rdfs:label ?answerLabel .\n    FILTER NOT EXISTS {{ ?answer {property_ref} ?known . }}"
        else:
            triple = f"?answer rdfs:label ?answerLabel .\n    FILTER NOT EXISTS {{ ?known {property_ref} ?answer . }}"

        candidate_filter = ""
        if negated and movie_question:
            candidate_filter = "?answer wdt:P31 wd:Q11424 ."

        if count:
            return f"""{PREFIXES}
SELECT (COUNT(DISTINCT ?answer) AS ?count) WHERE {{
    ?known rdfs:label ?knownLabel .
    FILTER(LCASE(STR(?knownLabel)) = LCASE({label_literal}))
    {triple}
    {candidate_filter}
    {filter_clause}
}}
"""

        return f"""{PREFIXES}
SELECT DISTINCT ?answer ?answerLabel WHERE {{
    ?known rdfs:label ?knownLabel .
    FILTER(LCASE(STR(?knownLabel)) = LCASE({label_literal}))
    {triple}
    {candidate_filter}
    {filter_clause}
    OPTIONAL {{
        ?answer rdfs:label ?answerLabel .
        FILTER(LANG(?answerLabel) = "" || LANGMATCHES(LANG(?answerLabel), "en"))
    }}
}}
"""

    def _extract_filter_clause(self, question, pid):
        """Translate simple date/numeric constraints into SPARQL filters."""
        q = self._normalize(question)
        filters = []

        years = re.findall(r"\b(?:18|19|20)\d{2}\b", q)
        if years and pid == "P577":
            year = years[0]
            if re.search(r"\b(before|earlier than|prior to)\b", q):
                filters.append(f'YEAR(?answer) < {year}')
            elif re.search(r"\b(after|later than|since)\b", q):
                filters.append(f'YEAR(?answer) > {year}')
            elif re.search(r"\b(in|during)\s+" + year + r"\b", q):
                filters.append(f'YEAR(?answer) = {year}')

        return "\n    ".join(f"FILTER({item})" for item in filters)

    def _build_global_release_query(self, question, count=False, negated=False):
        """Query release-date constraints that do not name one entity."""
        q = self._normalize(question)
        years = re.findall(r"\b(?:18|19|20)\d{2}\b", q)
        if not years:
            return None

        year = years[0]
        if re.search(r"\b(before|earlier than|prior to)\b", q):
            comparison = f"YEAR(?date) < {year}"
        elif re.search(r"\b(after|later than|since)\b", q):
            comparison = f"YEAR(?date) > {year}"
        elif re.search(r"\b(in|during)\s+" + year + r"\b", q):
            comparison = f"YEAR(?date) = {year}"
        else:
            return None

        select = (
            "SELECT (COUNT(DISTINCT ?movie) AS ?count)"
            if count
            else "SELECT DISTINCT ?answer ?answerLabel"
        )
        projection = "" if count else "BIND(?movie AS ?answer)"
        if negated:
            comparison = f"NOT ({comparison})"

        return f"""{PREFIXES}
{select} WHERE {{
    ?movie wdt:P577 ?date .
    FILTER({comparison})
    {projection}
    {{
        ?movie rdfs:label ?answerLabel .
        FILTER(LANG(?answerLabel) = "" || LANGMATCHES(LANG(?answerLabel), "en"))
    }}
}}
"""

    def _direct_global_release_answers(self, question, count=False, negated=False):
        q = self._normalize(question)
        years = re.findall(r"\b(?:18|19|20)\d{2}\b", q)
        if not years:
            return None
        year = int(years[0])
        if re.search(r"\b(before|earlier than|prior to)\b", q):
            matches = lambda value: value < year
        elif re.search(r"\b(after|later than|since)\b", q):
            matches = lambda value: value > year
        elif re.search(r"\b(in|during)\s+" + str(year) + r"\b", q):
            matches = lambda value: value == year
        else:
            return None

        date_predicate = URIRef(WDT + "P577")
        # Some course graph movie entities have a release date but no explicit
        # P31=film triple. Use P577 as the reliable movie/date universe.
        films = set(self.graph.subjects(predicate=date_predicate))
        answers = set()
        for film in films:
            if any(
                str(date)[:4].isdigit() and matches(int(str(date)[:4]))
                for date in self.graph.objects(film, date_predicate)
            ):
                answers.add(self.preferred_label_by_subject.get(film, str(film)))
        if negated:
            # Recompute against the complement of the date predicate. This
            # keeps the direct RDFLib path consistent with the SPARQL query.
            all_films = set(self.graph.subjects(predicate=date_predicate))
            matching = set()
            for film in all_films:
                if any(
                    str(date)[:4].isdigit() and matches(int(str(date)[:4]))
                    for date in self.graph.objects(film, date_predicate)
                ):
                    matching.add(film)
            answers = {
                self.preferred_label_by_subject.get(film, str(film))
                for film in all_films - matching
            }

        values = sorted(answers, key=str.casefold)
        return [str(len(values))] if count else values

    def _direct_global_release_superlative(self, question):
        """Return the earliest/latest release matching a year filter."""
        q = self._normalize(question)
        years = re.findall(r"\b(?:18|19|20)\d{2}\b", q)
        if not years:
            return None
        year = int(years[0])
        if re.search(r"\b(before|earlier than|prior to)\b", q):
            matches = lambda value: value < year
        elif re.search(r"\b(after|later than|since)\b", q):
            matches = lambda value: value > year
        elif re.search(r"\b(in|during)\s+" + str(year) + r"\b", q):
            matches = lambda value: value == year
        else:
            return None

        latest = any(word in q for word in ("latest", "newest", "most recent"))
        earliest = any(word in q for word in ("first", "earliest", "oldest"))
        if not (latest or earliest):
            return None

        candidates = []
        for movie in self.graph.subjects(predicate=URIRef(WDT + "P577")):
            for date in self.graph.objects(movie, URIRef(WDT + "P577")):
                date_text = str(date)
                if date_text[:4].isdigit() and matches(int(date_text[:4])):
                    label = self.preferred_label_by_subject.get(movie, str(movie))
                    candidates.append((int(date_text[:4]), label))
        if not candidates:
            return []
        candidates.sort(key=lambda item: (item[0], item[1].casefold()), reverse=latest)
        return [candidates[0][1]]

    def _build_superlative_query(self, mention, filter_pid, descending=False):
        label_literal = self._literal_n3(mention)
        order = "DESC" if descending else "ASC"
        return f"""{PREFIXES}
SELECT DISTINCT ?answer ?answerLabel ?date WHERE {{
    ?known rdfs:label ?knownLabel .
    FILTER(LCASE(STR(?knownLabel)) = LCASE({label_literal}))
    ?answer wdt:{filter_pid} ?known .
    ?answer wdt:P577 ?date .
    ?answer rdfs:label ?answerLabel .
    FILTER(LANG(?answerLabel) = "" || LANGMATCHES(LANG(?answerLabel), "en"))
}}
ORDER BY {order}(?date)
LIMIT 1
"""

    def _direct_superlative_answer(self, mention, filter_pid, descending=False):
        known_subjects = self.label_subjects.get(self._normalize(mention), set())
        relation = URIRef(WDT + filter_pid)
        date_predicate = URIRef(WDT + "P577")
        choices = []
        for known in known_subjects:
            for movie in self.graph.subjects(relation, known):
                for date in self.graph.objects(movie, date_predicate):
                    date_text = str(date)
                    if date_text[:4].isdigit():
                        choices.append((date_text, movie))
        if not choices:
            return []
        choices.sort(reverse=descending, key=lambda item: item[0])
        movie = choices[0][1]
        return [self.preferred_label_by_subject.get(movie, self.sparql_agent._pretty_value(movie))]

    def _extract_answers(self, result, preferred_key="answer"):
        if isinstance(result, dict) and "error" in result:
            return [], result["error"]
        if isinstance(result, bool):
            return ["true" if result else "false"], None
        if not isinstance(result, list):
            return [str(result)], None

        answers = []
        for row in result:
            if not isinstance(row, dict):
                continue

            if "count" in row and row.get("count") is not None:
                value = row.get("count")
            elif row.get("answerLabel"):
                value = row.get("answerLabel")
            else:
                value = row.get(preferred_key)

            if value is None:
                continue

            value = self.sparql_agent._pretty_value(value)
            if value not in answers:
                answers.append(value)

        return answers, None

    @staticmethod
    def _join_answers(answers, limit=None):
        if not answers:
            return ""
        truncated = limit is not None and len(answers) > limit
        if truncated:
            answers = answers[:limit]
        if len(answers) == 1:
            joined = answers[0]
        elif len(answers) == 2:
            joined = f"{answers[0]} and {answers[1]}"
        else:
            joined = ", ".join(answers[:-1]) + f", and {answers[-1]}"
        return f"{joined}, ..." if truncated else joined

    def _run_query(self, query, direct_answers=None):
        if os.environ.get("DEBUG_LOGGING", "").lower() in {"1", "true", "yes"}:
            print("\nGenerated SPARQL:")
            print(query.strip())
        if direct_answers is not None:
            return direct_answers, None
        result = self.sparql_agent.answer(query)
        answers, error = self._extract_answers(result)
        return answers, error

    def _direct_single_hop_answers(
        self,
        mention,
        pid,
        direction,
        count=False,
        negated=False,
        movie_question=False,
        value_universe=False,
    ):
        """Answer a simple relation from RDFLib indexes without invoking its
        comparatively expensive SPARQL parser and label scan."""
        known_subjects = self.label_subjects.get(self._normalize(mention), set())
        predicate = URIRef(WDT + pid)

        if not known_subjects:
            return []

        if not negated:
            values = set()
            for known in known_subjects:
                if direction == "head":
                    values.update(self.graph.subjects(predicate=predicate, object=known))
                else:
                    values.update(self.graph.objects(subject=known, predicate=predicate))
        else:
            candidates = set(self.preferred_label_by_subject)
            if movie_question:
                candidates = set(
                    self.graph.subjects(
                        predicate=URIRef(WDT + "P31"),
                        object=URIRef("http://www.wikidata.org/entity/Q11424"),
                    )
                )
            elif value_universe:
                candidates = set(self.graph.objects(None, predicate))
            values = set()
            for candidate in candidates:
                if direction == "head":
                    linked = any(
                        value in known_subjects
                        for value in self.graph.objects(candidate, predicate)
                    )
                else:
                    linked = any(
                        value in known_subjects
                        for value in self.graph.subjects(predicate, candidate)
                    )
                if not linked:
                    values.add(candidate)

        answers = []
        for value in values:
            if hasattr(value, "datatype") and value.datatype:
                text = str(value)
            else:
                text = self.preferred_label_by_subject.get(value, self.sparql_agent._pretty_value(value))
            if text not in answers:
                answers.append(text)
        answers.sort(key=str.casefold)
        return [str(len(answers))] if count else answers

    def _answer_superlative(self, question, mention):
        q = self._normalize(question)
        earliest = any(word in q for word in ("earliest", "oldest", "first released", "first release"))
        latest = any(word in q for word in ("latest", "newest", "most recent", "most recently"))
        if not (earliest or latest):
            return None

        # Stage 2's published example asks for the earliest film by a director.
        # This also generalises to cast/composer/screenwriter/etc. when phrased
        # as a movie-selection question.
        if not any(word in q for word in ("movie", "movies", "film", "films")):
            return None

        filter_pid = self._detect_relation(question, exclude={"P577"})
        if not filter_pid:
            return None

        query = self._build_superlative_query(
            mention=mention,
            filter_pid=filter_pid,
            descending=latest,
        )
        direct_answers = self._direct_superlative_answer(
            mention, filter_pid, descending=latest
        )
        answers, error = self._run_query(query, direct_answers=direct_answers)
        if error:
            return f"I could not execute the generated SPARQL query: {error}"
        if not answers:
            return "I could not find a factual answer in the knowledge graph."
        return self._join_answers(answers)

    def answer_natural_language(self, question):
        clean_question = self._strip_instruction(question)
        normalized_question = self._normalize(clean_question)
        pid = self._detect_relation(clean_question)

        # Handle global release-date superlatives before entity extraction;
        # generic graph labels such as "heist film" must not become entities.
        if (
            pid == "P577"
            and re.search(r"\b(?:first|earliest|oldest|latest|newest|most recent)\b", normalized_question)
            and re.search(r"\b(?:before|after|in|during|since)\b", normalized_question)
            and re.search(r"\b(?:movie|movies|film|films)\b", normalized_question)
        ):
            superlative_answers = self._direct_global_release_superlative(clean_question)
            if superlative_answers is not None:
                return self._join_answers(superlative_answers)

        mention = self._extract_entity_mention(clean_question)

        if not mention:
            count = bool(re.search(
                r"^(how many|what is the number of|number of|count the|count how many)",
                normalized_question,
            ))
            if pid == "P577":
                negated = self._is_negated(clean_question)
                superlative_answers = self._direct_global_release_superlative(clean_question)
                if superlative_answers is not None:
                    return self._join_answers(superlative_answers)
                global_query = self._build_global_release_query(
                    clean_question,
                    count=count,
                    negated=negated,
                )
                if global_query:
                    direct_answers = self._direct_global_release_answers(
                        clean_question,
                        count=count,
                        negated=negated,
                    )
                    answers, error = self._run_query(
                        global_query, direct_answers=direct_answers
                    )
                    if error:
                        return f"I could not execute the generated SPARQL query: {error}"
                    if answers:
                        limit = None if count else 4
                        return self._join_answers(answers, limit=limit)
                    return "I could not find a factual answer in the knowledge graph."
            return (
                "I could not identify the entity in the question. "
                "Try putting the movie or person name in quotes."
            )

        special = self._answer_superlative(clean_question, mention)
        if special is not None:
            return special

        if not pid:
            return (
                "I could not identify which knowledge-graph relation the question asks for."
            )

        count = bool(re.search(
            r"^(how many|what is the number of|number of|count the|count how many)",
            normalized_question,
        ))
        negated = self._is_negated(clean_question)
        filter_clause = self._extract_filter_clause(clean_question, pid)
        preferred_direction = self._infer_direction(clean_question)
        directions = [preferred_direction, "head" if preferred_direction == "tail" else "tail"]

        last_error = None
        for direction in directions:
            query = self._build_single_hop_query(
                mention=mention,
                pid=pid,
                direction=direction,
                count=count,
                negated=negated,
                filter_clause=filter_clause,
                movie_question=bool(re.search(r"\b(movie|movies|film|films)\b", normalized_question)),
            )
            direct_answers = None
            if not filter_clause and (
                not negated
                or bool(re.search(r"\b(movie|movies|film|films|award|awards|country|countries)\b", normalized_question))
            ):
                direct_answers = self._direct_single_hop_answers(
                    mention=mention,
                    pid=pid,
                    direction=direction,
                    count=count,
                    negated=negated,
                    movie_question=bool(re.search(r"\b(movie|movies|film|films)\b", normalized_question)),
                    value_universe=bool(re.search(r"\b(award|awards|country|countries)\b", normalized_question)),
                )
            answers, error = self._run_query(query, direct_answers=direct_answers)
            if error:
                last_error = error
                continue

            # COUNT always returns one row, including zero. If the preferred
            # direction gives zero, try the reverse direction before accepting.
            if count and answers == ["0"] and direction == preferred_direction:
                continue

            if answers:
                limit = 4 if (negated or filter_clause) and not count else None
                return self._join_answers(answers, limit=limit)

        if last_error:
            return f"I could not execute the generated SPARQL query: {last_error}"
        return "I could not find a factual answer in the knowledge graph."

    def handle_message(self, text):
        if not isinstance(text, str) or not text.strip():
            return "Please send a non-empty question."

        text = text.strip()
        if self._is_sparql(text):
            result = self.sparql_agent.answer(text)
            return self.sparql_agent.format_answer(result)

        return self.answer_natural_language(text)
