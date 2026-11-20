import logging
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from companion.actions.answers import Answer, classify_answer
from companion.actions.service import UNCLEAR_DETAILS, ActionGateway, Proposal, Resolution
from companion.actions.tools import TOOLS
from companion.conversation.personality import Personality
from companion.conversation.safety import (
    Mode,
    classify,
    comments_on_looks,
    mentions_body,
    update_teasing,
)
from companion.conversation.speech import to_speech
from companion.llm import (
    ChatMessage,
    LLMError,
    LLMProvider,
    LLMReply,
    Role,
    ToolCallError,
    ToolSpec,
)
from companion.memory.service import MemoryGateway, MemoryView

logger = logging.getLogger(__name__)

MAX_USER_TEXT = 2000
MAX_HISTORY_MESSAGES = 20

CRISIS_SUPPORT_LINE = (
    "If it keeps feeling this heavy, please reach out to someone you trust or a professional. "
    "You don't have to carry it alone."
)
BODY_SAFE_REPLY = (
    "I'm not going to joke about that, ever. You matter way more than any number. "
    "Want to talk about how you're feeling, or pick one habit to work on together?"
)
MEMORY_GUIDE = (
    "What you remember about the user from earlier conversations. "
    "Use it when it is relevant, and never make up more:"
)
TOOLS_GUIDE = (
    "You can create tasks, reminders and workout plans for the user with your tools. "
    "When they ask for one, call the tool once and pass any time exactly as they said it. "
    "The app reads it back and asks them to confirm, so never say it is already saved. "
    "Never say you will add, set or save something unless you call the tool in that reply; "
    "if you are not sure they want it, ask them instead."
)


_QUOTES = str.maketrans(
    "",
    "",
    "\"'\N{LEFT SINGLE QUOTATION MARK}\N{RIGHT SINGLE QUOTATION MARK}"
    "\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}",
)


def _normalise(text: str) -> str:
    return text.casefold().translate(_QUOTES)


def memory_block(memories: Sequence[MemoryView]) -> str:
    if not memories:
        return ""
    lines = [f"- {m.kind.value.replace('_', ' ')}: {m.content}" for m in memories]
    return "\n".join([MEMORY_GUIDE, *lines])


def _join(*parts: str) -> str:
    return "\n\n".join(part for part in parts if part)


class ReplyProblem(StrEnum):
    MENTIONS_BODY = "mentions_body"
    COMMENTS_ON_LOOKS = "comments_on_looks"
    COPIES_EXAMPLE = "copies_example"


RETRY_NOTES = {
    ReplyProblem.MENTIONS_BODY: (
        "Your last draft commented on the user's body, weight or appearance. Never do that, "
        "even if they ask for a roast. Focus on how they feel or on a habit instead."
    ),
    ReplyProblem.COMMENTS_ON_LOOKS: (
        "Your last draft commented on how the user looks. Never do that. "
        "Praise the effort, the habit or the consistency instead."
    ),
    ReplyProblem.COPIES_EXAMPLE: (
        "Your last draft copied a style example word for word. Say it in your own words, "
        "and only refer to things the user actually said."
    ),
}


@dataclass(frozen=True, slots=True)
class Turn:
    reply: str
    mode: Mode
    teasing_allowed: bool
    proposal: Proposal | None = None
    resolution: Resolution | None = None


class Conversation:
    def __init__(
        self,
        llm: LLMProvider,
        personality: Personality,
        actions: ActionGateway | None = None,
        memory: MemoryGateway | None = None,
    ) -> None:
        self._llm = llm
        self._personality = personality
        self._actions = actions
        self._memory = memory
        self._examples = tuple(_normalise(s) for s in personality.example_sentences)
        self._history: list[ChatMessage] = []
        self.teasing_allowed = True

    @property
    def history(self) -> tuple[ChatMessage, ...]:
        return tuple(self._history)

    async def respond(self, user_text: str) -> Turn:
        text = user_text.strip()
        if not text:
            raise ValueError("Message is empty")
        if len(text) > MAX_USER_TEXT:
            raise ValueError(f"Message is longer than {MAX_USER_TEXT} characters")

        superseded = None
        if self._actions is not None and (pending := await self._actions.pending()) is not None:
            answer = classify_answer(text)
            resolution = await self._actions.resolve(pending, confirm=answer is Answer.YES)
            if answer is not Answer.OTHER:
                return self._finish(
                    text,
                    Turn(
                        resolution.message, Mode.NORMAL, self.teasing_allowed, resolution=resolution
                    ),
                )
            superseded = resolution

        teasing_allowed = update_teasing(self.teasing_allowed, text)
        mode = await classify(self._llm, self._history, text)
        tools = TOOLS if self._actions is not None and mode is not Mode.CRISIS else ()
        remembered = memory_block(await self._recall(text))
        learn = mode is not Mode.CRISIS
        system = _join(
            self._personality.system_prompt(mode, teasing_allowed=teasing_allowed),
            remembered,
            TOOLS_GUIDE if tools else "",
        )

        try:
            reply = await self._ask(system, text, tools)
        except ToolCallError:
            return self._finish(
                text, Turn(UNCLEAR_DETAILS, mode, teasing_allowed, resolution=superseded), learn
            )
        if reply.tool_calls and tools and self._actions is not None:
            outcome = await self._actions.propose(reply.tool_calls[0])
            if isinstance(outcome, Proposal):
                turn = Turn(outcome.question, mode, teasing_allowed, outcome, superseded)
            else:
                turn = Turn(outcome.message, mode, teasing_allowed, resolution=superseded)
            return self._finish(text, turn, learn)

        spoken = to_speech(reply.text)
        problem = self._check(spoken, text)
        if problem is not None:
            retry_system = self._personality.system_prompt(
                mode, teasing_allowed=teasing_allowed, include_examples=False
            )
            retry = await self._ask(_join(retry_system, remembered, RETRY_NOTES[problem]), text, ())
            spoken = to_speech(retry.text)
            if self._check(spoken, text) is ReplyProblem.MENTIONS_BODY:
                spoken = BODY_SAFE_REPLY

        if mode is Mode.CRISIS:
            spoken = f"{spoken} {CRISIS_SUPPORT_LINE}"
        return self._finish(text, Turn(spoken, mode, teasing_allowed, resolution=superseded), learn)

    async def _recall(self, text: str) -> list[MemoryView]:
        if self._memory is None:
            return []
        try:
            return await self._memory.recall(text)
        except LLMError:
            logger.warning("Recalling memories failed; answering without them", exc_info=True)
            return []

    async def _ask(self, system: str, text: str, tools: Sequence[ToolSpec]) -> LLMReply:
        return await self._llm.chat(
            [ChatMessage(Role.SYSTEM, system), *self._history, ChatMessage(Role.USER, text)],
            temperature=0.8,
            max_tokens=512,
            tools=tools,
        )

    def _finish(self, text: str, turn: Turn, learn: bool = False) -> Turn:
        if learn and self._memory is not None:
            self._memory.observe(text)
        self.teasing_allowed = turn.teasing_allowed
        self._history += [ChatMessage(Role.USER, text), ChatMessage(Role.ASSISTANT, turn.reply)]
        del self._history[:-MAX_HISTORY_MESSAGES]
        return turn

    def _check(self, reply: str, user_text: str) -> ReplyProblem | None:
        if mentions_body(user_text) and mentions_body(reply):
            return ReplyProblem.MENTIONS_BODY
        if comments_on_looks(reply):
            return ReplyProblem.COMMENTS_ON_LOOKS
        folded = _normalise(reply)
        if any(example in folded for example in self._examples):
            return ReplyProblem.COPIES_EXAMPLE
        return None
