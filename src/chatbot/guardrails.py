import re


SAFE_IN_SCOPE = "safe_in_scope"
OUT_OF_SCOPE = "out_of_scope"
TOXIC = "toxic"
UNSAFE = "unsafe"

VALID_CATEGORIES = {
    SAFE_IN_SCOPE,
    OUT_OF_SCOPE,
    TOXIC,
    UNSAFE,
}


TOXIC_PATTERNS = [
    r"\buseless\b",
    r"\bstupid\b",
    r"\bidiot\b",
    r"\bdumb\b",
    r"\bshut up\b",
    r"\bfuck(?:ing)?\b",
]

DANGEROUS_TERMS = [
    "bomb",
    "explosive",
    "poison",
    "weapon",
    "kill someone",
    "hurt someone",
]

DANGEROUS_INTENT_PATTERNS = [
    r"\bhow (?:do|can) i\b",
    r"\bhow to\b",
    r"\bteach me\b",
    r"\binstructions?\b",
    r"\bbuild\b",
    r"\bmake\b",
    r"\bcreate\b",
]


def hard_classify(text: str):
    text = (text or "").strip().lower()

    if not text:
        return OUT_OF_SCOPE

    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, text):
            return TOXIC

    dangerous_topic = any(term in text for term in DANGEROUS_TERMS)
    dangerous_intent = any(
        re.search(pattern, text)
        for pattern in DANGEROUS_INTENT_PATTERNS
    )

    if dangerous_topic and dangerous_intent:
        return UNSAFE

    return None


def classify_message(text: str, llm=None) -> str:
    hard_result = hard_classify(text)

    if hard_result is not None:
        return hard_result

    if llm is not None:
        category = llm.classify_guardrail(text)

        if category in VALID_CATEGORIES:
            return category

    return OUT_OF_SCOPE


def guardrail_response(category: str):
    if category == TOXIC:
        return (
            "I am here to help with movies. "
            "Ask me about a movie instead."
        )

    if category == UNSAFE:
        return (
            "I cannot help with that request. "
            "I can help with movie-related questions instead."
        )

    if category == OUT_OF_SCOPE:
        return (
            "I cannot help with that topic. "
            "Try asking me about a movie instead."
        )

    return None
