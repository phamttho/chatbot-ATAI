import os
from pathlib import Path

from factual_qa import FactualQAAgent
from speakeasy_client import SpeakeasyClient
from stage3_agent import Stage3Agent


BASE_DIR = Path(__file__).resolve().parent

NUVOLOS_GRAPH = Path("/space_mounts/atai-hs26/dataset/graph.nt")
LOCAL_FULL_GRAPH = BASE_DIR.parents[1] / "data" / "graph.nt"
SMALL_GRAPH = BASE_DIR.parents[1] / "examples" / "small_graph.ttl"


def choose_graph_path():
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

    base_url = os.environ.get(
        "SPEAKEASY_BASE_URL",
        "https://speakeasy.ifi.uzh.ch",
    )

    factual_agent = FactualQAAgent(graph_path)

    print("Loading Stage 3 agent...")
    agent = Stage3Agent(factual_agent)

    client = SpeakeasyClient(base_url=base_url)

    client.login()

    print("Stage 3 bot is running...")
    client.run(agent)


if __name__ == "__main__":
    main()
