import os
from pathlib import Path

from movie_agent import MovieAgent
from speakeasy_client import SpeakeasyClient


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

    model_name = os.environ.get("MOVIE_LLM_MODEL", "Qwen/Qwen3.5-4B")
    print(f"Loading movie agent: {model_name}")
    agent = MovieAgent(graph_path, model_name=model_name)

    # The benchmark includes requests above the client's old five-second limit.
    os.environ.setdefault("MESSAGE_TIMEOUT_SECONDS", "90")

    client = SpeakeasyClient(base_url=base_url)

    client.login()

    print(f"Speakeasy bot is running with {model_name}...")
    client.run(agent)


if __name__ == "__main__":
    main()
