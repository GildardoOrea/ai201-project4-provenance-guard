LLM_WEIGHT = 0.65
STYLOMETRIC_WEIGHT = 0.35

AI_THRESHOLD = 0.75
HUMAN_THRESHOLD = 0.25


def combine_signals(llm_ai_prob: float, stylometric_ai_prob: float) -> float:
    score = LLM_WEIGHT * llm_ai_prob + STYLOMETRIC_WEIGHT * stylometric_ai_prob
    return round(max(0.0, min(1.0, score)), 4)


def classify(confidence: float) -> str:
    if confidence >= AI_THRESHOLD:
        return "likely_ai"
    if confidence <= HUMAN_THRESHOLD:
        return "likely_human"
    return "uncertain"


def generate_label(confidence: float) -> str:
    pct = round(confidence * 100)
    attribution = classify(confidence)

    if attribution == "likely_ai":
        return (
            f"This content shows strong signals of AI generation. Our system is {pct}% "
            "confident this was AI-generated, based on language-model and writing-style analysis. "
            "The creator can appeal this classification."
        )
    if attribution == "likely_human":
        return (
            f"This content shows strong signals of human authorship. Our system is {100 - pct}% "
            "confident this was written by a person, based on language-model and writing-style analysis."
        )
    return (
        "We can't confidently determine whether this content is AI-generated or human-written. "
        f"Our analysis is inconclusive ({pct}% AI-likelihood). Treat this attribution as provisional."
    )
