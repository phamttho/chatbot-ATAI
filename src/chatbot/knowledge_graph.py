from pathlib import Path
from typing import Any

from rdflib import BNode, Graph, Literal, URIRef


class SPARQLAgent:
    """Execute plain SPARQL queries against a local RDF knowledge graph."""

    def __init__(self, graph_path):
        self.graph_path = Path(graph_path)

        if not self.graph_path.exists():
            raise FileNotFoundError(
                f"Knowledge graph not found: {self.graph_path.resolve()}"
            )

        extension = self.graph_path.suffix.lower()
        formats = {
            ".ttl": "turtle",
            ".nt": "nt",
            ".rdf": "xml",
            ".xml": "xml",
            ".n3": "n3",
            ".jsonld": "json-ld",
        }
        rdf_format = formats.get(extension)

        if rdf_format is None:
            raise ValueError(f"Unsupported RDF format: {extension}")

        self.graph = Graph()
        print(f"Loading knowledge graph: {self.graph_path}")
        self.graph.parse(self.graph_path, format=rdf_format)
        print(f"Loaded {len(self.graph):,} triples.")

    def handle_message(self, text: str) -> str:
        """Process one Speakeasy message and return the text to send back."""
        if not isinstance(text, str) or not text.strip():
            return "Please send a non-empty SPARQL query."

        result = self.answer(text)
        return self.format_answer(result)

    def answer(self, query: str) -> Any:
        """Execute a SPARQL query. Stage 1 supports SELECT and ASK."""
        if not isinstance(query, str) or not query.strip():
            return {"error": "SPARQL query is empty."}

        try:
            result = self.graph.query(query)
        except Exception as error:
            return {"error": f"SPARQL query failed: {error}"}

        if result.type == "ASK":
            return bool(result.askAnswer)

        if result.type == "SELECT":
            return self._parse_select(result)

        return {"error": f"Unsupported SPARQL query type: {result.type}"}

    def _parse_select(self, result):
        answers = []
        variables = [str(variable) for variable in result.vars]

        for row in result:
            item = {}
            for variable, value in zip(variables, row):
                item[variable] = None if value is None else self._convert_value(value)
            answers.append(item)

        return answers

    @staticmethod
    def _convert_value(value):
        """Convert RDFLib terms into serializable Python strings."""
        if isinstance(value, (URIRef, Literal, BNode)):
            return str(value)
        return str(value)

    def format_answer(self, result) -> str:
        """Turn RDFLib query results into a compact Speakeasy response."""
        if isinstance(result, dict) and "error" in result:
            return result["error"]

        if isinstance(result, bool):
            return "true" if result else "false"

        if not result:
            return "No results found."

        # Common case: one aggregate, date, rating, count, etc.
        if len(result) == 1 and len(result[0]) == 1:
            value = next(iter(result[0].values()))
            return self._pretty_value(value)

        output = []

        for row in result:
            # Course examples commonly use ?answerLabel and ?answerItem.
            # Keep the Q-ID because it is useful for debugging and is accepted
            # by the example format, while the human-readable label comes first.
            if "answerLabel" in row and "answerItem" in row:
                label = row["answerLabel"]
                entity = self._entity_id(row["answerItem"])
                output.append(
                    f"{label} ({entity})" if entity else self._pretty_value(label)
                )
                continue

            if "movieLabel" in row and "movieItem" in row:
                label = row["movieLabel"]
                entity = self._entity_id(row["movieItem"])
                output.append(
                    f"{label} ({entity})" if entity else self._pretty_value(label)
                )
                continue

            if len(row) == 1:
                output.append(self._pretty_value(next(iter(row.values()))))
                continue

            output.append(" | ".join(self._pretty_value(value) for value in row.values()))

        return ", ".join(output)

    @staticmethod
    def _entity_id(uri):
        if uri is None:
            return ""
        value = str(uri)
        return value.rsplit("/", 1)[-1] if "/" in value else value

    def _pretty_value(self, value):
        if value is None:
            return ""

        value = str(value)
        if value.startswith("http://www.wikidata.org/entity/"):
            return self._entity_id(value)
        return value
