from guardrails import classify_message, guardrail_response, SAFE_IN_SCOPE
from llm_client import LocalLLM


class Stage3Agent:
    def __init__(self, factual_agent):
        self.factual_agent = factual_agent
        self.llm = LocalLLM()

    def handle_message(self, text: str) -> str:
        category = classify_message(text)

        print(f"Guardrail classification: {category}")

        # Block / redirect anything that is not safe movie content.
        if category != SAFE_IN_SCOPE:
            return guardrail_response(category)

        # Safe movie questions first use our Stage 2 knowledge-graph system.
        try:
            if hasattr(self.factual_agent, "handle_message"):
                answer = self.factual_agent.handle_message(text)
            else:
                result = self.factual_agent.answer(text)
                answer = self.factual_agent.format_answer(result)

            if answer and "could not" not in answer.lower() and "no results" not in answer.lower():
                return answer

        except Exception as error:
            print("Factual QA failed:", error)

        # Fallback for safe movie-related conversation.
        return self.llm.generate(text)
