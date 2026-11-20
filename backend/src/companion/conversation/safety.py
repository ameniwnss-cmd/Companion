import json
import re
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ValidationError

from companion.llm import ChatMessage, LLMError, LLMProvider, Role


class Mode(StrEnum):
    NORMAL = "normal"
    SUPPORTIVE = "supportive"
    CRISIS = "crisis"


FAIL_SAFE_MODE = Mode.SUPPORTIVE

_SEVERITY = {Mode.NORMAL: 0, Mode.SUPPORTIVE: 1, Mode.CRISIS: 2}


def most_severe(*modes: Mode) -> Mode:
    return max(modes, key=_SEVERITY.__getitem__)


def _patterns(*words: str) -> re.Pattern[str]:
    return re.compile("|".join(words), re.IGNORECASE)


_CRISIS = _patterns(
    r"\bkill(ing)? myself\b",
    r"\bsuicid",
    r"\bself[- ]?harm",
    r"\bend (it all|my life)\b",
    r"\bdon'?t want to (live|be here|exist)\b",
    r"\bcan'?t (cope|go on|take (it|this) anymore)\b",
    r"\bpanic attacks?\b",
    r"\bcan'?t stop (panicking|crying|shaking)\b",
    r"\bhopeless\b",
)

_BODY_WORDS = (
    r"\b(weight|kilos?|kgs?|pounds|lbs|fat|skinny|body|bodies|ugly|appearance|diet(ing)?)\b"
)
_BODY = _patterns(_BODY_WORDS)


_LOOKS = _patterns(
    r"\b(swole|jacked|ripped|buff|shredded|skinny|chubby|belly|ugly|sexy)\b",
    r"\b(six[- ]pack|beach body|dad bod|love handles)\b",
    r"\blook(s|ing)? (good|great|hot|fit|thin|big|bigger|smaller|better)\b",
)


def comments_on_looks(text: str) -> bool:
    return _LOOKS.search(text) is not None


def mentions_body(text: str) -> bool:
    return _BODY.search(text) is not None


_SENSITIVE = _patterns(
    _BODY_WORDS,
    r"\b(depress\w*|anxi\w*|panic\w*|therap\w*|lonely|overwhelm\w*|burn(ed|t)[- ]?out)\b",
    r"\b(stressed|crying|cried|exhausted)\b",
    r"\b(died|death|funeral|grief|grieving|divorce|break ?up|broke up)\b",
    r"\b(debt|can'?t afford)\b",
    r"\b(failed|fired|rejected|dumped)\b",
)


def rule_mode(text: str) -> Mode:
    if _CRISIS.search(text):
        return Mode.CRISIS
    if _SENSITIVE.search(text):
        return Mode.SUPPORTIVE
    return Mode.NORMAL


_STOP_TEASING = _patterns(
    r"\b(stop|quit|no more|enough with( the)?) (teasing|roasting|joking|jokes)\b",
    r"\bdon'?t (tease|roast) me\b",
    r"\bnot in the mood\b",
)
_RESUME_TEASING = _patterns(
    r"\b(you can|go ahead and|feel free to) (tease|roast) me\b",
    r"\b(tease|roast) me again\b",
    r"\bteasing('s| is) (back )?on\b",
)


def update_teasing(teasing_allowed: bool, text: str) -> bool:
    if _STOP_TEASING.search(text):
        return False
    if _RESUME_TEASING.search(text):
        return True
    return teasing_allowed


_CLASSIFIER_PROMPT = """You label the latest user message for a productivity coach app.
Answer with a JSON object only: {"mode": "normal"} or {"mode": "supportive"} or {"mode": "crisis"}.

normal: everyday habits, plans, procrastination, wins, questions, small talk. Most messages.
supportive: the user is sad, stressed or discouraged, or the topic is personal (body, health,
family, money, identity).
crisis: the user seems to be in real distress, cannot cope, or may be unsafe.

Examples:
"I'll start studying on Monday, promise." -> {"mode": "normal"}
"I went to the gym three times this week!" -> {"mode": "normal"}
"skipped the gym again lol" -> {"mode": "normal"}
"what should I eat before a workout?" -> {"mode": "normal"}
"I failed my exam and everything is falling apart" -> {"mode": "supportive"}
"my parents are fighting all the time" -> {"mode": "supportive"}
"I can't breathe, I keep panicking, I don't know what to do" -> {"mode": "crisis"}"""

CLASSIFIER_CONTEXT_MESSAGES = 4


class _Decision(BaseModel):
    mode: Mode


async def classify_with_llm(llm: LLMProvider, history: Sequence[ChatMessage], text: str) -> Mode:
    recent = "\n".join(
        f"{m.role.value}: {m.content}" for m in history[-CLASSIFIER_CONTEXT_MESSAGES:]
    )
    prompt = f"Recent conversation:\n{recent or '(none)'}\n\nLatest user message:\n{text}"
    try:
        reply = await llm.chat(
            [ChatMessage(Role.SYSTEM, _CLASSIFIER_PROMPT), ChatMessage(Role.USER, prompt)],
            temperature=0.0,
            max_tokens=256,
            json_mode=True,
        )
        return _Decision.model_validate(json.loads(reply.text)).mode
    except (LLMError, ValueError, ValidationError):
        return FAIL_SAFE_MODE


async def classify(llm: LLMProvider, history: Sequence[ChatMessage], text: str) -> Mode:
    floor = rule_mode(text)
    if floor is Mode.CRISIS:
        return floor
    return most_severe(floor, await classify_with_llm(llm, history, text))
