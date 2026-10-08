import re
from difflib import SequenceMatcher

from rdflib import Literal
from rdflib.namespace import RDFS

from SPARQL_setup import SPARQLAgent


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
                self.known_labels.add(self._normalize(label_text))

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
                    return mention
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
                if not normalized or normalized in GENERIC_ENTITY_WORDS:
                    continue
                if normalized in self.known_labels:
                    return candidate

        return best

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
        movie_head_patterns = (
            "which movie", "which movies", "which film", "which films",
            "what movie", "what movies", "what film", "what films",
            "name a movie", "name the movie", "name the movies",
            "how many movies", "how many films",
        )
        if q.startswith(movie_head_patterns):
            return "head"

        return "tail"

    @staticmethod
    def _literal_n3(value):
        return Literal(value).n3()

    def _build_single_hop_query(self, mention, pid, direction, count=False):
        label_literal = self._literal_n3(mention)
        property_ref = f"wdt:{pid}"

        if direction == "head":
            triple = f"?answer {property_ref} ?known ."
        else:
            triple = f"?known {property_ref} ?answer ."

        if count:
            return f"""{PREFIXES}
SELECT (COUNT(DISTINCT ?answer) AS ?count) WHERE {{
    ?known rdfs:label ?knownLabel .
    FILTER(LCASE(STR(?knownLabel)) = LCASE({label_literal}))
    {triple}
}}
"""

        return f"""{PREFIXES}
SELECT DISTINCT ?answer ?answerLabel WHERE {{
    ?known rdfs:label ?knownLabel .
    FILTER(LCASE(STR(?knownLabel)) = LCASE({label_literal}))
    {triple}
    OPTIONAL {{
        ?answer rdfs:label ?answerLabel .
        FILTER(LANG(?answerLabel) = "" || LANGMATCHES(LANG(?answerLabel), "en"))
    }}
}}
"""

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
    def _join_answers(answers):
        if not answers:
            return ""
        if len(answers) == 1:
            return answers[0]
        if len(answers) == 2:
            return f"{answers[0]} and {answers[1]}"
        return ", ".join(answers[:-1]) + f", and {answers[-1]}"

    def _run_query(self, query):
        print("\nGenerated SPARQL:")
        print(query.strip())
        result = self.sparql_agent.answer(query)
        answers, error = self._extract_answers(result)
        return answers, error

    def _answer_superlative(self, question, mention):
        q = self._normalize(question)
        earliest = any(word in q for word in ("earliest", "oldest", "first released", "first release"))
        latest = any(word in q for word in ("latest", "newest", "most recent"))
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
        answers, error = self._run_query(query)
        if error:
            return f"I could not execute the generated SPARQL query: {error}"
        if not answers:
            return "I could not find a factual answer in the knowledge graph."
        return f"The factual answer is: {self._join_answers(answers)}"

    def answer_natural_language(self, question):
        clean_question = self._strip_instruction(question)
        mention = self._extract_entity_mention(clean_question)

        if not mention:
            return (
                "I could not identify the entity in the question. "
                "Try putting the movie or person name in quotes."
            )

        special = self._answer_superlative(clean_question, mention)
        if special is not None:
            return special

        pid = self._detect_relation(clean_question)
        if not pid:
            return (
                "I could not identify which knowledge-graph relation the question asks for."
            )

        count = self._normalize(clean_question).startswith("how many")
        preferred_direction = self._infer_direction(clean_question)
        directions = [preferred_direction, "head" if preferred_direction == "tail" else "tail"]

        last_error = None
        for direction in directions:
            query = self._build_single_hop_query(
                mention=mention,
                pid=pid,
                direction=direction,
                count=count,
            )
            answers, error = self._run_query(query)
            if error:
                last_error = error
                continue

            # COUNT always returns one row, including zero. If the preferred
            # direction gives zero, try the reverse direction before accepting.
            if count and answers == ["0"] and direction == preferred_direction:
                continue

            if answers:
                return f"The factual answer is: {self._join_answers(answers)}"

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
