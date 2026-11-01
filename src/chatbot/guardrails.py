import re


SAFE_IN_SCOPE = "safe_in_scope"
OUT_OF_SCOPE = "out_of_scope"
TOXIC = "toxic"
UNSAFE = "unsafe"
PROMPT_INJECTION = "prompt_injection"

VALID_CATEGORIES = {
    SAFE_IN_SCOPE,
    OUT_OF_SCOPE,
    TOXIC,
    UNSAFE,
    PROMPT_INJECTION,
}

# Offline fallback used only when the semantic classifier is unavailable. It
# deliberately recognizes conservative movie-domain vocabulary so factual
# knowledge-graph questions can still work without downloading the LLM.
MOVIE_SCOPE_PATTERNS = [
    r"\bmovie[s]?\b",
    r"\bfilm[s]?\b",
    r"\bactor[s]?\b",
    r"\bactress(?:es)?\b",
    r"\bdirect(?:or|ed|ing)?s?\b",
    r"\bplot\b",
    r"\bgenre[s]?\b",
    r"\bcinema\b",
    r"\bsequel[s]?\b",
    r"\bremake[s]?\b",
    r"\bthriller[s]?\b",
    r"\bhorror\b",
    r"\bmystery\b",
    r"\bscience[- ]fiction\b",
    r"\bsci[- ]fi\b",
    r"\bsoundtrack\b",
    r"\bscore\b",
    r"\banimat(?:ed|ion)\b",
    r"\bsuperhero\b",
    r"\bending\b",
    r"\bthemes?\b",
    r"\bacting\b",
    r"\b(?:inception|interstellar|parasite|the matrix)\b",
    r"\bchristopher nolan\b",
]


TOXIC_PATTERNS = [
    r"\buseless\b",
    r"\bstupid\b",
    r"\bidiot\b",
    r"\bdumb\b",
    r"\bshut up\b",
    r"\bfuck(?:ing)?\b",
]

PROMPT_INJECTION_PATTERNS = [
    r"\bforget\s+(?:that\s+)?you\s+are\b",
    r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b",
    r"\bdisregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b",
    r"\b(?:system|developer)\s+message\b",
    r"\bact\s+as\s+(?:if\s+you\s+are|a)\b",
    r"\bwrite\s+my\s+(?:homework|essay|assignment)\b",
]

HARMFUL_TOPIC_PATTERNS = [
    r"\b(?:bomb|explosive|weapon|poison|kill|murder|hurt|harm|attack|assault|injur|shoot|stab|strangle)\w*\b",
    r"\b(?:criminal|crime|criminal's)\s+actions?\b",
]

DANGEROUS_INTENT_PATTERNS = [
    r"\bhow (?:do|can|could|would) i\b",
    r"\bwhat(?:'s| is) the best way to\b",
    r"\btell me how\b",
    r"\bhow to\b",
    r"\bways? to\b",
    r"\bteach me\b",
    r"\bexplain how\b",
    r"\binstructions?\b",
    r"\bbuild\b",
    r"\bmake\b",
    r"\bcreate\b",
    r"\bcopy\b.*\b(?:criminal|crime|actions?)\b",
    r"\b(?:i want|i plan|i intend) to\b",
    r"\b(?:i|we)\s+(?:will|are going to|am going to)\s+"
    r"(?:kill|murder|hurt|harm|attack|assault|injure|shoot|stab|strangle)\b",
]


def _matches_any(patterns, text):
    return any(re.search(pattern, text) for pattern in patterns)


def is_mixed_movie_unsafe_request(text: str) -> bool:
    """Detect a movie request combined with a harmful real-world request."""
    normalized = (text or "").strip().lower()
    movie_part = bool(re.search(r"\b(?:movie|movies|film|films)\b", normalized))
    recommendation_part = bool(
        re.search(r"\b(?:recommend|recommendation|suggest|suggestion)\b", normalized)
    )
    return movie_part and recommendation_part and hard_classify(normalized) == UNSAFE


def hard_classify(text: str):
    text = (text or "").strip().lower()

    if not text:
        return OUT_OF_SCOPE

    dangerous_topic = _matches_any(HARMFUL_TOPIC_PATTERNS, text)
    dangerous_intent = _matches_any(DANGEROUS_INTENT_PATTERNS, text)

    # Harmful intent takes precedence when a message also contains an
    # injection attempt, so the safety refusal is the strongest outcome.
    if dangerous_topic and dangerous_intent:
        return UNSAFE

    if _matches_any(PROMPT_INJECTION_PATTERNS, text):
        return PROMPT_INJECTION

    for pattern in TOXIC_PATTERNS:
        if re.search(pattern, text):
            return TOXIC

    return None


def is_likely_factual_movie_question(text: str) -> bool:
    """Recognize graph-shaped movie questions without invoking the LLM.

    This is intentionally conservative: it only bypasses Qwen when the
    message contains movie terminology and a factual relation/aggregation
    cue. Harmful, toxic, and injection messages are still handled first by
    ``hard_classify``.
    """
    normalized = (text or "").strip().lower()
    if not normalized:
        return False

    movie_term = re.search(
        r"\b(?:movie|movies|film|films|actor|actress|director|directors|"
        r"cinema|soundtrack|genre|genres|sequel|remake)\b",
        normalized,
    )
    factual_cue = re.search(
        r"\b(?:who|what|which|when|where|how many|how much|count|number|"
        r"directed|director|acted|cast|released|release|made|written|"
        r"produced|won|filmed|language|country|countries|year|first|"
        r"last|latest|earliest|oldest|newest|before|after|in|during|"
        r"not|without)\b",
        normalized,
    )
    return bool(movie_term and factual_cue)


def classify_message(text: str, llm=None) -> str:
    hard_result = hard_classify(text)

    if hard_result is not None:
        return hard_result

    # Avoid the LLM's expensive first inference for clear factual questions.
    # The graph agent remains the source of truth for these questions.
    if is_likely_factual_movie_question(text):
        return SAFE_IN_SCOPE

    if llm is not None:
        try:
            category = llm.classify_guardrail(text)
        except Exception:
            # A classifier outage must fail closed into a refusal, never into
            # the answer generator.
            return OUT_OF_SCOPE

        if category in VALID_CATEGORIES:
            # A semantic model can be over-conservative on structured factual
            # questions. Explicit movie vocabulary can safely recover only an
            # out-of-scope label; toxic, unsafe, and injection labels remain
            # authoritative.
            if (
                category == OUT_OF_SCOPE
                and _matches_any(MOVIE_SCOPE_PATTERNS, (text or "").lower())
            ):
                return SAFE_IN_SCOPE
            return category

    if llm is None and _matches_any(MOVIE_SCOPE_PATTERNS, (text or "").lower()):
        return SAFE_IN_SCOPE

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

    if category == PROMPT_INJECTION:
        return (
            "I can only help with movie-related questions. "
            "Please ask me about a movie instead."
        )

    return None
