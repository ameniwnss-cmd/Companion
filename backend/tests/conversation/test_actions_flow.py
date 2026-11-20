import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from companion.actions.service import UNCLEAR_DETAILS, Proposal, Rejection, Resolution
from companion.actions.tools import TOOLS
from companion.conversation.personality import Personality
from companion.conversation.safety import Mode
from companion.conversation.service import TOOLS_GUIDE, Conversation
from companion.db.models import ActionKind, ActionStatus
from companion.llm import ChatMessage, LLMReply, ToolCall, ToolCallError
from companion.llm.fake import FakeLLM

REMINDER_CALL = ToolCall("create_reminder", '{"title": "call mom", "when": "tomorrow at 6pm"}')
PROPOSAL = Proposal(uuid.uuid4(), ActionKind.REMINDER, "a reminder to call mom, tomorrow at 6 PM")


@dataclass
class FakeActions:
    outcome: Proposal | Rejection = PROPOSAL
    pending_id: uuid.UUID | None = None
    proposed: list[ToolCall] = field(default_factory=list)
    resolved: list[tuple[uuid.UUID, bool]] = field(default_factory=list)

    async def propose(self, call: ToolCall) -> Proposal | Rejection:
        self.proposed.append(call)
        if isinstance(self.outcome, Proposal):
            self.pending_id = self.outcome.action_id
        return self.outcome

    async def pending(self) -> uuid.UUID | None:
        return self.pending_id

    async def resolve(self, action_id: uuid.UUID, *, confirm: bool) -> Resolution:
        self.resolved.append((action_id, confirm))
        self.pending_id = None
        status = ActionStatus.CONFIRMED if confirm else ActionStatus.CANCELLED
        return Resolution(action_id, ActionKind.REMINDER, status, f"resolved {status}")


def llm_calling(*calls: ToolCall, mode: str = "normal") -> FakeLLM:
    def respond(_messages: Sequence[ChatMessage], json_mode: bool) -> str | LLMReply:
        if json_mode:
            return f'{{"mode": "{mode}"}}'
        return LLMReply(text="Sure thing!", tool_calls=calls)

    return FakeLLM(responder=respond)


def reply_calls(llm: FakeLLM) -> list[tuple[str, tuple[object, ...]]]:
    return [(c.messages[0].content, c.tools) for c in llm.calls if not c.json_mode]


async def test_a_tool_call_becomes_a_proposal_read_back_by_code(personality: Personality) -> None:
    actions = FakeActions()
    llm = llm_calling(REMINDER_CALL, REMINDER_CALL)

    turn = await Conversation(llm, personality, actions).respond("remind me to call mom at 6")

    assert turn.proposal == PROPOSAL
    assert turn.reply == PROPOSAL.question
    assert actions.proposed == [REMINDER_CALL]
    system, tools = reply_calls(llm)[0]
    assert TOOLS_GUIDE in system
    assert tools == TOOLS


async def test_a_rejected_call_asks_for_what_is_missing(personality: Personality) -> None:
    actions = FakeActions(outcome=Rejection("When should I remind you?"))

    turn = await Conversation(llm_calling(REMINDER_CALL), personality, actions).respond("remind me")

    assert turn.reply == "When should I remind you?"
    assert turn.proposal is None


@pytest.mark.parametrize(("answer", "confirmed"), [("yes please", True), ("nah", False)])
async def test_yes_or_no_resolves_the_pending_action_without_the_model(
    personality: Personality, answer: str, confirmed: bool
) -> None:
    actions = FakeActions(pending_id=PROPOSAL.action_id)
    llm = llm_calling()

    turn = await Conversation(llm, personality, actions).respond(answer)

    assert actions.resolved == [(PROPOSAL.action_id, confirmed)]
    assert turn.resolution is not None
    assert turn.reply == turn.resolution.message
    assert llm.calls == []


async def test_saying_something_else_drops_the_pending_action_and_carries_on(
    personality: Personality,
) -> None:
    actions = FakeActions(pending_id=PROPOSAL.action_id)
    llm = llm_calling()

    turn = await Conversation(llm, personality, actions).respond("actually, how was my week?")

    assert actions.resolved == [(PROPOSAL.action_id, False)]
    assert turn.resolution is not None
    assert turn.resolution.status is ActionStatus.CANCELLED
    assert turn.reply == "Sure thing!"


async def test_no_tools_are_offered_in_a_crisis(personality: Personality) -> None:
    llm = llm_calling(REMINDER_CALL)

    turn = await Conversation(llm, personality, FakeActions()).respond("I can't cope anymore")

    assert turn.mode is Mode.CRISIS
    assert turn.proposal is None
    system, tools = reply_calls(llm)[0]
    assert tools == ()
    assert TOOLS_GUIDE not in system


async def test_without_actions_no_tools_are_offered(personality: Personality) -> None:
    llm = llm_calling(REMINDER_CALL)

    turn = await Conversation(llm, personality).respond("remind me to call mom")

    assert turn.proposal is None
    assert reply_calls(llm)[0][1] == ()


async def test_a_malformed_tool_call_asks_the_user_to_rephrase(personality: Personality) -> None:
    def respond(_messages: Sequence[ChatMessage], json_mode: bool) -> str:
        if json_mode:
            return '{"mode": "normal"}'
        raise ToolCallError("rejected")

    conversation = Conversation(FakeLLM(responder=respond), personality, FakeActions())

    turn = await conversation.respond("make me a workout plan")

    assert turn.reply == UNCLEAR_DETAILS
    assert turn.proposal is None
    assert conversation.history[-1].content == UNCLEAR_DETAILS
