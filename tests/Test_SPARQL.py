import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "chatbot"
sys.path.insert(0, str(SRC_DIR))

from knowledge_graph import SPARQLAgent


BASE_DIR = Path(__file__).resolve().parents[1]
GRAPH_PATH = BASE_DIR / "examples" / "small_graph.ttl"
agent = SPARQLAgent(GRAPH_PATH)


def run_test(name, query):
    print("\n" + "=" * 70)
    print(name)
    print("=" * 70)
    print("\nSPARQL:")
    print(query)

    result = agent.answer(query)

    print("\nRAW RESULT:")
    print(result)
    print("\nFORMATTED ANSWER:")
    print(agent.format_answer(result))


query1 = """
SELECT ?subject ?predicate ?object
WHERE {
    ?subject ?predicate ?object .
}
LIMIT 10
"""
run_test("TEST 1 - First 10 triples", query1)

query2 = """
SELECT ?movie ?title
WHERE {
    ?movie <http://example.org/property/title> ?title .
}
"""
run_test("TEST 2 - Movie titles", query2)

query3 = """
SELECT ?rating
WHERE {
    ?movie <http://example.org/property/title>
           "Star Wars Episode VII: The Force Awakens" .
    ?movie <http://example.org/property/rating> ?rating .
}
"""
run_test("TEST 3 - Star Wars rating", query3)

query4 = """
SELECT ?tag
WHERE {
    ?movie <http://example.org/property/title>
           "Star Wars Episode VII: The Force Awakens" .
    ?movie <http://example.org/property/tag> ?tag .
}
"""
run_test("TEST 4 - Star Wars tags", query4)

query5 = """
SELECT (COUNT(DISTINCT ?movie) AS ?count)
WHERE {
    ?movie <http://example.org/property/title> ?title .
}
"""
run_test("TEST 5 - Number of movies", query5)

query6 = """
ASK {
    ?movie <http://example.org/property/title>
           "Star Wars Episode VII: The Force Awakens" .
}
"""
run_test("TEST 6 - Does Star Wars exist?", query6)

# Confirm malformed input does not crash the program.
run_test("TEST 7 - Invalid SPARQL", "SELECT WHERE { ??? }")
