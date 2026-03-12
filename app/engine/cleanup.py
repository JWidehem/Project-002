import re

_LEVELS: dict[str, list[int]] = {
    "none":   [],
    "light":  [1, 2],
    "medium": [1, 2, 3],
}


def clean(
    text: str,
    level: str = "light",
    filler_words: list[str] | None = None,
) -> str:
    if not text:
        return text

    passes = _LEVELS.get(level, _LEVELS["light"])

    # Pass 1: remove filler words
    if 1 in passes and filler_words:
        pattern = r'\b(' + "|".join(re.escape(w) for w in filler_words) + r')\b'
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.UNICODE)
        text = re.sub(r" {2,}", " ", text).strip()

    # Pass 2: deduplicate immediate repetitions
    if 2 in passes:
        text = re.sub(
            r"\b(\w+)(\s+\1)+\b", r"\1", text,
            flags=re.IGNORECASE | re.UNICODE,
        )

    # Pass 3: punctuation normalisation
    if 3 in passes:
        text = re.sub(r"\s+([,\.!?])", r"\1", text)
        sentence_boundary_found = bool(re.search(r"[\.!?]\s+\w", text))
        text = re.sub(
            r"([\.!?])\s+(\w)",
            lambda m: m.group(1) + " " + m.group(2).upper(),
            text,
        )
        if text and sentence_boundary_found:
            text = text[0].upper() + text[1:]

    return text.strip()
