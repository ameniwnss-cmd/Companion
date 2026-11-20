import re
from enum import StrEnum


class Answer(StrEnum):
    YES = "yes"
    NO = "no"
    UNDO = "undo"
    OTHER = "other"


MAX_ANSWER_WORDS = 8

_YES = {
    "yes",
    "yeah",
    "yea",
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
    "definitely",
    "correct",
    "right",
}
_YES_PHRASES = ("do it", "save it", "save them", "go ahead", "sounds good", "please do")
_NO = {"no", "nope", "nah", "cancel", "don't", "dont", "never", "scrap", "forget", "not"}
_UNDO_PHRASES = ("undo", "take it back", "take that back", "revert")
_LEADING_FILLER = {"oh", "um", "uh", "erm", "hmm", "ah", "well", "so"}
_CHANGES_THE_REQUEST = {
    "but",
    "instead",
    "change",
    "make",
    "actually",
    "wait",
    "move",
    "also",
    "and",
    "add",
    "another",
    "remind",
    "need",
    "except",
    "earlier",
    "later",
}

_WORD = re.compile(r"[a-z']+")


def classify_answer(text: str) -> Answer:
    words = _WORD.findall(text.lower().replace("\N{RIGHT SINGLE QUOTATION MARK}", "'"))
    if not words or len(words) > MAX_ANSWER_WORDS:
        return Answer.OTHER
    if any(word in _CHANGES_THE_REQUEST for word in words):
        return Answer.OTHER

    while len(words) > 1 and words[0] in _LEADING_FILLER:
        words = words[1:]
    joined = " ".join(words)

    if joined.startswith(_UNDO_PHRASES):
        return Answer.UNDO
    if words[0] in _NO:
        return Answer.NO
    if words[0] in _YES or joined.startswith(_YES_PHRASES):
        return Answer.YES
    return Answer.OTHER
