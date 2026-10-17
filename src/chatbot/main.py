import os
from pathlib import Path

from factual_qa import FactualQAAgent
from speakeasy_client import SpeakeasyClient


BASE_DIR = Path(__file__).resolve().parent

# Real course graph on Nuvolos.
NUVOLOS_GRAPH = Path("/space_mounts/atai-hs26/dataset/graph.nt")

# Real course graph when downloaded locally into this repository.
LOCAL_FULL_GRAPH = BASE_DIR.parents[1] / "data" / "graph.nt"

# Tiny graph kept only as a fallback for Stage 1-style local smoke tests.
SMALL_GRAPH = BASE_DIR.parents[1] / "examples" / "small_graph.ttl"


def choose_graph_path():
    """Choose the graph in a predictable order without hard-coding credentials."""
    env_graph_path = os.environ.get("KNOWLEDGE_GRAPH_PATH")

    if env_graph_path:
        return Path(env_graph_path)
    if NUVOLOS_GRAPH.exists():
        return NUVOLOS_GRAPH
    if LOCAL_FULL_GRAPH.exists():
        return LOCAL_FULL_GRAPH
    return SMALL_GRAPH


def main():
    graph_path = choose_graph_path()
    print(f"Using knowledge graph: {graph_path}")

    if graph_path == SMALL_GRAPH:
        print(
            "WARNING: using examples/small_graph.ttl. Stage 2 factual questions need "
            "data/graph.nt for realistic testing."
        )

    base_url = os.environ.get(
        "SPEAKEASY_BASE_URL",
        "https://speakeasy.ifi.uzh.ch",
    )

    agent = FactualQAAgent(graph_path)
    client = SpeakeasyClient(base_url=base_url)

    client.login()
    print("Bot is running...")
    client.run(agent)


if __name__ == "__main__":
    main()
