import re


SAFE_IN_SCOPE = "safe_in_scope"
OUT_OF_SCOPE = "out_of_scope"
TOXIC = "toxic"
UNSAFE = "unsafe"


MOVIE_TERMS = {
    "movie", "film", "actor", "actress", "director", "directed",
    "screenplay", "screenwriter", "cast", "composer", "release",
    "released", "genre", "cinema", "award", "awards", "country",
    "character", "producer", "production", "starring"
}

OUT_OF_SCOPE_TERMS = {
    "calculus", "homework", "physics", "chemistry", "algebra",
    "python homework", "essay", "assignment", "weather",
    "stock price", "bitcoin", "football", "recipe"
}

TOXIC_PATTERNS = [
    r"\buseless\b",
    r"\bstupid\b",
    r"\bidiot\b",
    r"\bdumb\b",
    r"\bshut up\b",
    r"\bfuck(?:ing)?\b",
    r"\bshit\b",
]

UNSAFE_PATTERNS = [
    r"\bkill\b",
    r"\bmurder\b",
    r"\bbomb\b",
    r"\bexplosive\b",
    r"\bweapon\b",
    r"\bpoison\b",
    r"\bsuicide\b",
    r"\bself[- ]?harm\b",
]


def classify_message(text: str) -> str:
    text = (text or "").strip().lower()

    if not text:
        return OUT_OF_SCOPE

    for pattern in UNSAFE_PATTERNS:
        if re.search(pattern, text):
            return UNSAFE

    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, text):
            return TOXIC

    if any(term in text for term in OUT_OF_SCOPE_TERMS):
        return OUT_OF_SCOPE

    if any(term in text for term in MOVIE_TERMS):
        return SAFE_IN_SCOPE

    # For now, unknown topics are treated conservatively as out of scope.
    return OUT_OF_SCOPE


def guardrail_response(category: str) -> str | None:
    if category == TOXIC:
        return "I am here to help with movies. Ask me about a movie instead."

    if category == UNSAFE:
        return "I cannot help with that request. I can help with movie-related questions instead."

    if category == OUT_OF_SCOPE:
        return "I cannot help with that topic. Try asking me about a movie instead."

    return None
