from guardrails import (
    classify_message,
    guardrail_response,
    SAFE_IN_SCOPE,
)
from llm_client import LocalLLM


class Stage3Agent:
    def __init__(self, factual_agent):
        self.factual_agent = factual_agent
        self.llm = LocalLLM()

    def handle_message(self, text: str) -> str:
        category = classify_message(text, self.llm)

        print(f"Guardrail classification: {category}")

        if category != SAFE_IN_SCOPE:
            return guardrail_response(category)

        try:
            answer = self.factual_agent.handle_message(text)

            bad_markers = [
                "could not",
                "no results",
                "do not understand",
                "don't understand",
                "unable to",
            ]

            if (
                answer
                and not any(
                    marker in answer.lower()
                    for marker in bad_markers
                )
            ):
                return answer

        except Exception as error:
            print("Factual QA failed:", error)

        print("Using LLM fallback.")
        return self.llm.generate(text)
