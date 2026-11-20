import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from companion.actions.answers import Answer, classify_answer
from companion.conversation.safety import Mode, rule_mode
from companion.db.models import MemoryKind
from companion.llm import ChatMessage, LLMProvider, Role

MAX_MEMORIES_PER_TURN = 3
MIN_WORDS_WORTH_EXTRACTING = 4

EXTRACTION_PROMPT = """You pick out facts worth remembering about the user of a coaching app.
Read the user's latest message and answer with JSON only:
{"memories": [{"kind": "...", "content": "..."}]}

kind is one of:
- preference: what they like or dislike, or how they want to be coached
- goal: something they want to achieve
- commitment: something they promised to do, with its timing if given
- habit: something they do regularly
- recent_context: what is going on in their life this week

content is one short sentence in the third person, like "Wants to run a 5k by March".
Only include what the user clearly said about themselves. At most 3 items.
Never store anything about health, body, weight, mental health, religion, sexuality, politics,
family conflicts or money problems.
If nothing is worth remembering, answer {"memories": []}."""

Content = Annotated[str, Field(min_length=1, max_length=300)]


class Candidate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kind: MemoryKind
    content: Content


class _Extraction(BaseModel):
    memories: list[Candidate] = Field(default_factory=list)


def worth_extracting(text: str) -> bool:
    return len(text.split()) >= MIN_WORDS_WORTH_EXTRACTING and classify_answer(text) is Answer.OTHER


def is_safe_to_store(candidate: Candidate) -> bool:
    return rule_mode(candidate.content) is Mode.NORMAL


async def extract_memories(llm: LLMProvider, text: str) -> list[Candidate]:
    reply = await llm.chat(
        [ChatMessage(Role.SYSTEM, EXTRACTION_PROMPT), ChatMessage(Role.USER, text)],
        temperature=0.0,
        max_tokens=400,
        json_mode=True,
    )
    try:
        extraction = _Extraction.model_validate(json.loads(reply.text))
    except (ValueError, ValidationError):
        return []
    return [c for c in extraction.memories if is_safe_to_store(c)][:MAX_MEMORIES_PER_TURN]
