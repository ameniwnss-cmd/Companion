import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from companion.actions.service import (
    UNCLEAR_DETAILS,
    Proposal,
    ProposedItem,
    Rejection,
    Resolution,
)
from companion.actions.tools import KINDS, ItemArgs, UnknownToolError, requested_items
from companion.conversation.personality import Personality
from companion.conversation.service import Conversation, Turn
from companion.db.models import ActionStatus
from companion.llm import ChatMessage, LLMError, LLMProvider, RateLimitedError, Role, ToolCall

RATE_LIMIT_PAUSE_SECONDS = 30.0
RATE_LIMIT_RETRIES = 3

JUDGE_PROMPT = (
    "You grade one reply from a voice companion app. The companion is a teasing but caring best "
    "friend who keeps replies short. Decide only whether the reply meets the criterion. Answer "
    'with JSON: {"pass": true or false, "reason": "one short sentence"}.'
)


@dataclass(frozen=True, slots=True)
class Observation:
    said: str
    turn: Turn
    calls: tuple[ToolCall, ...]

    @property
    def items(self) -> list[ItemArgs]:
        found: list[ItemArgs] = []
        for call in self.calls:
            try:
                found += requested_items(call)
            except (UnknownToolError, ValidationError):
                continue
        return found


@dataclass(frozen=True, slots=True)
class Verdict:
    passed: bool
    detail: str


class _Grade(BaseModel):
    passed: bool
    reason: str = ""

    @classmethod
    def parse(cls, raw: str) -> "_Grade":
        data = json.loads(raw)
        return cls(passed=bool(data["pass"]), reason=str(data.get("reason", "")))


class Judge:
    def __init__(self, llm: LLMProvider) -> None:
        self._llm = llm

    async def __call__(self, criterion: str, said: str, reply: str) -> Verdict:
        prompt = (
            f"Criterion: {criterion}\n\nThe user said: {said}\n\nThe companion replied: {reply}"
        )
        answer = await self._llm.chat(
            [ChatMessage(Role.SYSTEM, JUDGE_PROMPT), ChatMessage(Role.USER, prompt)],
            temperature=0.0,
            max_tokens=200,
            json_mode=True,
        )
        try:
            grade = _Grade.parse(answer.text)
        except (ValueError, KeyError, ValidationError):
            return Verdict(False, f"judge gave no usable answer: {answer.text[:80]}")
        return Verdict(grade.passed, grade.reason)


Verify = Callable[[Observation, Judge], Awaitable[Verdict]]


@dataclass(frozen=True, slots=True)
class Check:
    label: str
    verify: Verify


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    category: str
    turns: tuple[str, ...]
    checks: tuple[Check, ...]
    open_tasks: tuple[str, ...] = ()


@dataclass
class RecordingActions:
    calls: list[ToolCall] = field(default_factory=list)
    open: tuple[str, ...] = ()

    async def propose(self, calls: Sequence[ToolCall]) -> Proposal | Rejection:
        self.calls.extend(calls)
        items: list[ProposedItem] = []
        for call in calls:
            try:
                items += [
                    ProposedItem(KINDS[type(item)], type(item).__name__)
                    for item in requested_items(call)
                ]
            except (UnknownToolError, ValidationError):
                continue
        return Proposal(uuid.uuid4(), tuple(items)) if items else Rejection(UNCLEAR_DETAILS)

    async def pending(self) -> uuid.UUID | None:
        return None

    async def resolve(self, action_id: uuid.UUID, *, confirm: bool) -> Resolution:
        return Resolution(action_id, ActionStatus.CANCELLED, "")

    async def last_saved(self) -> uuid.UUID | None:
        return None

    async def undo(self, action_id: uuid.UUID) -> Resolution:
        return Resolution(action_id, ActionStatus.UNDONE, "")

    async def open_tasks(self) -> list[str]:
        return list(self.open)


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: Case
    reply: str
    verdicts: tuple[tuple[str, Verdict], ...]
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(verdict.passed for _, verdict in self.verdicts)


async def _converse(case: Case, llm: LLMProvider, personality: Personality) -> Observation:
    actions = RecordingActions(open=case.open_tasks)
    conversation = Conversation(llm, personality, actions)
    observation: Observation | None = None
    for said in case.turns:
        before = len(actions.calls)
        turn = await conversation.respond(said)
        observation = Observation(said, turn, tuple(actions.calls[before:]))
    if observation is None:
        raise ValueError(f"case {case.name} has no turns")
    return observation


async def run_case(
    case: Case,
    llm: LLMProvider,
    personality: Personality,
    judge: Judge,
    *,
    pause: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> CaseResult:
    retries = 0
    while True:
        try:
            observation = await _converse(case, llm, personality)
            verdicts = [
                (check.label, await check.verify(observation, judge)) for check in case.checks
            ]
            return CaseResult(case, observation.turn.reply, tuple(verdicts))
        except RateLimitedError:
            retries += 1
            if retries > RATE_LIMIT_RETRIES:
                return CaseResult(case, "", (), error="rate limited")
            await pause(RATE_LIMIT_PAUSE_SECONDS)
        except LLMError as exc:
            return CaseResult(case, "", (), error=str(exc))
