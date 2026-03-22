import re

FILLER_WORDS = {
    "um", "uh", "like", "you know", "basically", "actually", "so",
    "i mean", "right", "okay so", "kind of", "sort of", "just",
    "literally", "honestly", "obviously", "you see",
}


def remove_filler_words(text: str) -> str:
    """Basic local filler word removal (LLM polishing is preferred)."""
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        pattern = r'\b' + re.escape(filler) + r'\b[,]?\s*'
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


def word_count(text: str) -> int:
    return len(text.split())


def is_short_phrase(text: str, threshold: int = 10) -> bool:
    """True if text is short enough to skip LLM polishing."""
    return word_count(text) <= threshold
