import re

FILLER_WORDS = {
    "um", "uh", "uh huh", "hmm", "like", "you know", "basically",
    "actually", "so", "well", "i mean", "right", "okay so", "kind of",
    "sort of", "just", "literally", "honestly", "obviously", "you see",
    "so yeah", "you know what i mean", "i guess", "i think", "like i said",
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


def auto_capitalize(text: str) -> str:
    """Capitalize first letter, after sentence endings, and standalone 'i'."""
    if not text:
        return text
    text = text[0].upper() + text[1:]
    text = re.sub(r'([.!?]\s+)([a-z])', lambda m: m.group(1) + m.group(2).upper(), text)
    text = re.sub(r'\bi\b', 'I', text)
    return text


def smart_punctuation(text: str) -> str:
    """Light punctuation cleanup for raw STT output."""
    text = text.strip()
    if not text:
        return text
    # Fix double+ spaces
    text = re.sub(r'\s{2,}', ' ', text)
    # Fix spacing before punctuation
    text = re.sub(r'\s+([.,!?;:])', r'\1', text)
    # Add period at end if no terminal punctuation
    if text[-1] not in '.!?':
        text += '.'
    return text
