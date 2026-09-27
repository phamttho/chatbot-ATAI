from pathlib import Path

from SPARQL_setup import SPARQLAgent
from speakeasy_client import SpeakeasyClient


def main():
    # 1. Load knowledge graph
    graph_path = Path(__file__).resolve().parent / "small_graph.ttl"
    agent = SPARQLAgent(graph_path)

    # 2. Connect to Speakeasy
    client = SpeakeasyClient(
        base_url="https://speakeasy.ifi.uzh.ch"
    )

    client.login()

    print("Bot is running...")

    # 3. Start listening for messages
    client.run(agent)


if __name__ == "__main__":
    main()
