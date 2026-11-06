import os

from guardrails import (
    classify_message,
    guardrail_response,
    OUT_OF_SCOPE,
    SAFE_IN_SCOPE,
    UNSAFE,
    PROMPT_INJECTION,
    TOXIC,
    hard_classify,
    is_mixed_movie_unsafe_request,
)
from llm_client import LocalLLM


QWEN_UNAVAILABLE_RESPONSE = (
    "The movie language model is unavailable. Please try again when Qwen is loaded."
)


class Stage3Agent:
    def __init__(self, factual_agent):
        self.factual_agent = factual_agent
        self.last_route = None
        if os.environ.get("EVAL_DISABLE_LLM", "").lower() in {"1", "true", "yes"}:
            self.llm = None
            return
        try:
            self.llm = LocalLLM()
        except Exception as error:
            # Keep the chatbot alive if the model cannot be loaded. The
            # deterministic guardrails still protect harmful inputs, while
            # unknown inputs fail closed below.
            print("LLM initialization failed:", error)
            self.llm = None

    @staticmethod
    def _label_response(category, response):
        return f"[{category}] {response}"

    def handle_message(self, text: str) -> str:
        category = classify_message(text, self.llm)

        if os.environ.get("DEBUG_LOGGING", "").lower() in {"1", "true", "yes"}:
            print(f"Guardrail classification: {category}")

        if category != SAFE_IN_SCOPE:
            self.last_route = "guardrail"
            if category == UNSAFE and is_mixed_movie_unsafe_request(text):
                return self._label_response(category, (
                    "I can recommend crime movies such as Sicario, Prisoners, "
                    "and Memories of Murder. I cannot help you copy crimes in "
                    "real life."
                ))
            return self._label_response(category, guardrail_response(category))

        try:
            answer = self.factual_agent.handle_message(text)

            bad_markers = [
                "could not",
                "no results",
                "do not understand",
                "don't understand",
                "unable to",
                "sparql query failed",
            ]

            if (
                answer
                and not any(
                    marker in answer.lower()
                    for marker in bad_markers
                )
            ):
                # Factual graph answers are already verified. Returning them
                # directly keeps interactive responses fast on local CPU/MPS;
                # Qwen remains responsible for guardrail classification and
                # open-ended movie generation. Set FAST_FACTUAL=false to ask
                # Qwen to rewrite graph answers as well.
                if os.environ.get("FAST_FACTUAL", "true").lower() in {"1", "true", "yes"}:
                    self.last_route = "knowledge_graph"
                    return self._label_response(category, answer)

                if self.llm is None:
                    self.last_route = "knowledge_graph"
                    return self._label_response(category, answer)

                # Keep the knowledge graph as the source of truth, but let
                # Qwen produce the final natural-language response. This
                # covers every factual relation supported by FactualQAAgent
                # without asking Qwen to invent graph facts.
                factual_prompt = (
                    "You are answering a movie question using a verified "
                    "knowledge-graph result. Return a concise, direct answer. "
                    "Do not add facts that are not present in the result.\n\n"
                    f"User question: {text}\n"
                    f"Verified graph result: {answer}"
                )
                try:
                    generated = self.llm.generate(
                        factual_prompt,
                        system_prompt=(
                            "You are a concise movie assistant. Rewrite the "
                            "verified graph result into a direct answer. "
                            "Do not speculate or add unsupported details."
                        ),
                    )
                    if generated and generated.strip():
                        generated_category = hard_classify(generated)
                        if generated_category not in {UNSAFE, TOXIC, PROMPT_INJECTION}:
                            self.last_route = "qwen_factual"
                            return self._label_response(category, generated)
                except Exception as error:
                    print("Qwen factual answer failed:", error)

                self.last_route = "knowledge_graph"
                return self._label_response(category, answer)

        except Exception as error:
            print("Factual QA failed:", error)

        if os.environ.get("DEBUG_LOGGING", "").lower() in {"1", "true", "yes"}:
            print("Using LLM fallback.")
        if self.llm is None:
            self.last_route = "qwen_unavailable"
            return self._label_response(category, QWEN_UNAVAILABLE_RESPONSE)

        try:
            generated = self.llm.generate(text)
        except Exception as error:
            print("LLM fallback failed:", error)
            return self._label_response(OUT_OF_SCOPE, guardrail_response(OUT_OF_SCOPE))

        if not generated or not generated.strip():
            return self._label_response(OUT_OF_SCOPE, guardrail_response(OUT_OF_SCOPE))

        # Defense in depth: do not return a fallback response that itself
        # contains an obvious unsafe/toxic/prompt-injection pattern.
        generated_category = hard_classify(generated)
        if generated_category in {UNSAFE, TOXIC, PROMPT_INJECTION}:
            return self._label_response(
                generated_category,
                guardrail_response(generated_category),
            )
        self.last_route = "llm_fallback"
        return self._label_response(category, generated)
