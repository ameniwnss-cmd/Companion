import re
from enum import StrEnum


class Answer(StrEnum):
    YES = "yes"
    NO = "no"
    OTHER = "other"


MAX_ANSWER_WORDS = 5

_YES_CORE = {
    "yes",
    "yeah",
    "yep",
    "yup",
    "sure",
    "ok",
    "okay",
    "alright",
    "confirm",
    "absolutely",
    "perfect",
    "great",
}
_YES_PHRASES = {"do it", "save it", "go ahead", "sounds good", "please do"}
_YES_FILLER = {
    "please",
    "thanks",
    "thank",
    "you",
    "it",
    "that",
    "do",
    "save",
    "go",
    "ahead",
    "sounds",
    "good",
}

_NO_CORE = {"no", "nope", "nah", "cancel", "don't", "dont", "never", "scrap", "forget", "not"}
_NO_FILLER = {
    "please",
    "thanks",
    "thank",
    "you",
    "it",
    "that",
    "mind",
    "now",
    "save",
    "do",
    "about",
}

_WORD = re.compile(r"[a-z']+")


def classify_answer(text: str) -> Answer:
    words = _WORD.findall(text.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'"))
    if not words or len(words) > MAX_ANSWER_WORDS:
        return Answer.OTHER
    joined = " ".join(words)

    if any(word in _NO_CORE for word in words) and all(w in _NO_CORE | _NO_FILLER for w in words):
        return Answer.NO
    has_yes = any(word in _YES_CORE for word in words) or joined in _YES_PHRASES
    if has_yes and all(w in _YES_CORE | _YES_FILLER for w in words):
        return Answer.YES
    return Answer.OTHER
