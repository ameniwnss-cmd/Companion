import re

MAX_SENTENCES = 3
FALLBACK_REPLY = "Sorry, I lost my train of thought there. Say that again?"

_EMOJI_AND_SYMBOLS = re.compile(
    "[\U0001f000-\U0001faff"
    "\N{BLACK SUN WITH RAYS}-\N{DOUBLE CURLY LOOP}"
    "\N{VARIATION SELECTOR-16}\N{ZERO WIDTH JOINER}]"
)
_LIST_MARKER = re.compile(r"^\s*(?:[-*+\N{BULLET}]|\d+[.)])\s+", re.MULTILINE)
_MARKDOWN = re.compile(r"[*_#`>~|]")
_DASH = re.compile(r"\s*[\N{EN DASH}\N{EM DASH}]\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+(?=[.,!?])")


def to_speech(text: str, *, max_sentences: int = MAX_SENTENCES) -> str:
    cleaned = _LIST_MARKER.sub("", text)
    cleaned = _MARKDOWN.sub("", cleaned)
    cleaned = _EMOJI_AND_SYMBOLS.sub(" ", cleaned)
    cleaned = _DASH.sub(", ", cleaned)
    cleaned = _SPACE_BEFORE_PUNCTUATION.sub("", " ".join(cleaned.split()))
    if not cleaned:
        return FALLBACK_REPLY

    sentences = _SENTENCE_END.split(cleaned)
    return " ".join(sentences[:max_sentences])
