from pathlib import Path
from rdflib import Graph, URIRef, Literal, BNode


class SPARQLAgent:
    """
    Simple SPARQL agent for querying a local RDF KG.
    """

    def __init__(self, graph_path):
        self.graph_path = Path(graph_path)

        if not self.graph_path.exists():
            raise FileNotFoundError(
                f"Knowledge graph not found: {self.graph_path.resolve()}"
            )
        self.graph = Graph()
        print(f"Loading knowledge graph: {self.graph_path}")
        # Detect format from extension
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
            raise ValueError(
                f"Unsupported RDF format: {extension}"
            )

        self.graph.parse(
            self.graph_path,
            format=rdf_format
        )

        print(f"Loaded {len(self.graph):,} triples.")

    # -----------------------------------------------------
    # Execute SPARQL
    # -----------------------------------------------------

    def answer(self, query):
        """
        Execute a SPARQL query against the knowledge graph.

        Supports:
        - SELECT
        - ASK
        """

        try:
            result = self.graph.query(query)

        except Exception as e:
            return {
                "error": f"SPARQL query failed: {e}"
            }

        # ASK query
        if result.type == "ASK":
            return bool(result.askAnswer)

        # SELECT query
        if result.type == "SELECT":
            return self._parse_select(result)

        return {
            "error": f"Unsupported SPARQL query type: {result.type}"
        }

    # -----------------------------------------------------
    # Parse SELECT
    # -----------------------------------------------------

    def _parse_select(self, result):
        answers = []

        variables = [str(v) for v in result.vars]

        for row in result:
            item = {}

            for variable, value in zip(variables, row):

                if value is None:
                    item[variable] = None
                    continue

                item[variable] = self._convert_value(value)

            answers.append(item)

        return answers

    # -----------------------------------------------------
    # Convert RDF values
    # -----------------------------------------------------

    def _convert_value(self, value):
        """
        Convert RDFLib objects into normal Python strings.
        """

        if isinstance(value, URIRef):
            return str(value)

        if isinstance(value, Literal):
            return str(value)

        if isinstance(value, BNode):
            return str(value)

        return str(value)

    # -----------------------------------------------------
    # Human-readable output
    # -----------------------------------------------------

    def format_answer(self, result):
        """
        Convert query results into a simple answer suitable
        for sending back to Speakeasy.
        """

        if isinstance(result, dict) and "error" in result:
            return result["error"]

        # ASK
        if isinstance(result, bool):
            return "true" if result else "false"

        if not result:
            return "No results found."

        # Single row, single value
        if len(result) == 1 and len(result[0]) == 1:
            value = next(iter(result[0].values()))
            return self._pretty_value(value)

        output = []

        for row in result:

            # Common course format:
            #
            # ?answerLabel ?answerItem
            #
            if "answerLabel" in row and "answerItem" in row:
                label = row["answerLabel"]
                entity = self._entity_id(row["answerItem"])

                output.append(
                    f"{label} ({entity})"
                )

                continue

            # Another common format:
            #
            # ?movieLabel ?movieItem
            #
            if "movieLabel" in row and "movieItem" in row:
                label = row["movieLabel"]
                entity = self._entity_id(row["movieItem"])

                output.append(
                    f"{label} ({entity})"
                )

                continue

            # Generic single-column results
            if len(row) == 1:
                value = next(iter(row.values()))
                output.append(self._pretty_value(value))
                continue

            # Generic multi-column results
            values = []

            for value in row.values():
                values.append(self._pretty_value(value))

            output.append(" | ".join(values))

        return ", ".join(output)

    # -----------------------------------------------------
    # Helper methods
    # -----------------------------------------------------

    def _entity_id(self, uri):
        """
        Convert:
        http://www.wikidata.org/entity/Q455401

        into:
        Q455401
        """

        if uri is None:
            return ""

        uri = str(uri)

        if "/" in uri:
            return uri.rsplit("/", 1)[-1]

        return uri

    def _pretty_value(self, value):
        if value is None:
            return ""

        value = str(value)

        # Wikidata URI -> Q-ID
        if value.startswith(
            "http://www.wikidata.org/entity/"
        ):
            return self._entity_id(value)

        return value