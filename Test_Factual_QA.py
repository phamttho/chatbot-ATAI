from pathlib import Path

from factual_qa import FactualQAAgent


BASE_DIR = Path(__file__).resolve().parent
GRAPH_PATH = BASE_DIR / "dataset" / "graph.nt"


TESTS = [
    (
        "Handmaiden screenwriters",
        "Please answer this question with a factual approach: "
        "Who wrote the screenplay for 'The Handmaiden'?",
        ["Jeong Seo-kyeong", "Park Chan-wook"],
    ),
    (
        "Interstellar countries",
        "Please answer this question with a factual approach: "
        "What are the countries of origin of 'Interstellar'?",
        ["United States", "United Kingdom"],
    ),
    (
        "Manchester release date",
        "Please answer this question with a factual approach: "
        "When did the movie 'Manchester by the Sea' come out?",
        ["2016-01-23"],
    ),
    (
        "Sofia Coppola earliest film",
        "Please answer this question with a factual approach: "
        "Which movie directed by 'Sofia Coppola' has the earliest release date?",
        ["The Virgin Suicides"],
    ),
    (
        "There Will Be Blood awards",
        "Please answer this question with a factual approach: "
        "Which awards did the movie 'There Will Be Blood' receive?",
        [
            "Academy Award for Best Actor",
            "Academy Award for Best Cinematography",
            "Amanda Award for Best Foreign Feature Film",
        ],
    ),
    (
        "The Father composer",
        "Please answer this question: Who is the composer of 'The Father'?",
        ["Ludovico Einaudi"],
    ),
]


def main():
    if not GRAPH_PATH.exists():
        raise FileNotFoundError(
            "dataset/graph.nt was not found. Copy the downloaded course graph to "
            f"{GRAPH_PATH}"
        )

    agent = FactualQAAgent(GRAPH_PATH)
    failures = 0

    for name, question, expected_parts in TESTS:
        print("\n" + "=" * 80)
        print(name)
        print("=" * 80)
        print("QUESTION:")
        print(question)

        answer = agent.handle_message(question)
        print("\nANSWER:")
        print(answer)

        missing = [part for part in expected_parts if part not in answer]
        if missing:
            failures += 1
            print(f"\nFAILED - missing: {missing}")
        else:
            print("\nPASSED")

    print("\n" + "=" * 80)
    if failures:
        print(f"{failures} test(s) failed.")
        raise SystemExit(1)

    print("All Stage 2 example tests passed.")


if __name__ == "__main__":
    main()
