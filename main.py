import os
from pathlib import Path

from SPARQL_setup import SPARQLAgent
from speakeasy_client import SpeakeasyClient


BASE_DIR = Path(__file__).resolve().parent


def main():
    # Keep the sample graph as a default for local testing. On Nuvolos, point
    # KNOWLEDGE_GRAPH_PATH at the real course knowledge graph instead.
    graph_path = Path(
        os.environ.get("KNOWLEDGE_GRAPH_PATH", BASE_DIR / "small_graph.ttl")
    )

    base_url = os.environ.get(
        "SPEAKEASY_BASE_URL",
        "https://speakeasy.ifi.uzh.ch",
    )

    agent = SPARQLAgent(graph_path)
    client = SpeakeasyClient(base_url=base_url)

    client.login()
    print("Bot is running...")
    client.run(agent)


if __name__ == "__main__":
    main()
