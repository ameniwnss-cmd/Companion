import logging
import time
import uuid
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from companion.actions.service import ActionNotFoundError, Resolution, UserActions
from companion.conversation.safety import Mode
from companion.conversation.service import MAX_USER_TEXT, Conversation, Turn
from companion.db.models import ActionKind, ActionStatus
from companion.llm import LLMError, RateLimitedError
from companion.memory.extract import extract_memories
from companion.memory.service import UserMemory
from companion.speech.stt import SpeechError, SpeechToText
from companion.speech.tts import TextToSpeech, speech_clips
from companion.users import get_or_create_user, valid_timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dev", tags=["dev"])

NOT_HEARD = "I didn't catch that. Try again?"
TOO_LONG = "That recording is too long. Keep it under a minute."
RATE_LIMITED = "I'm getting a lot of messages at once. Give me a few seconds and try again."


class UserMessage(BaseModel):
    type: Literal["user_message"]
    text: Annotated[str, Field(min_length=1, max_length=MAX_USER_TEXT)]


class ResolveAction(BaseModel):
    type: Literal["resolve_action"]
    id: uuid.UUID
    confirm: bool


ClientEvent = TypeAdapter[UserMessage | ResolveAction](
    Annotated[UserMessage | ResolveAction, Field(discriminator="type")]
)


class StatusEvent(BaseModel):
    type: Literal["status"] = "status"
    state: Literal["idle", "thinking", "speaking"]


class UserTranscript(BaseModel):
    type: Literal["user_transcript"] = "user_transcript"
    text: str


class AssistantMessage(BaseModel):
    type: Literal["assistant_message"] = "assistant_message"
    text: str
    mode: Mode
    teasing_allowed: bool


class PendingActionEvent(BaseModel):
    type: Literal["pending_action"] = "pending_action"
    id: uuid.UUID
    kind: ActionKind
    summary: str


class ActionResolvedEvent(BaseModel):
    type: Literal["action_resolved"] = "action_resolved"
    id: uuid.UUID
    status: ActionStatus


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    detail: str


class _Channel:
    def __init__(
        self,
        websocket: WebSocket,
        conversation: Conversation,
        actions: UserActions,
        memory: UserMemory,
        listener: SpeechToText,
        voice: TextToSpeech | None,
        max_audio_bytes: int,
    ) -> None:
        self._ws = websocket
        self._conversation = conversation
        self._actions = actions
        self._memory = memory
        self._listener = listener
        self._voice = voice
        self._max_audio_bytes = max_audio_bytes

    async def send(self, event: BaseModel) -> None:
        await self._ws.send_text(event.model_dump_json())

    async def handle_text(self, raw: str) -> None:
        try:
            event = ClientEvent.validate_json(raw)
        except ValidationError:
            await self.send(ErrorEvent(detail="Invalid message"))
            return

        await self.send(StatusEvent(state="thinking"))
        if isinstance(event, UserMessage):
            await self._reply_to(event.text)
        else:
            await self._resolve(event)
        await self.send(StatusEvent(state="idle"))
        self._memory.release()

    async def handle_audio(self, audio: bytes) -> None:
        if len(audio) > self._max_audio_bytes:
            await self.send(ErrorEvent(detail=TOO_LONG))
            return

        await self.send(StatusEvent(state="thinking"))
        try:
            transcript = await self._listener.transcribe(audio)
        except SpeechError:
            logger.warning("Transcription failed", exc_info=True)
            transcript = ""
        if transcript:
            await self.send(UserTranscript(text=transcript))
            await self._reply_to(transcript)
        else:
            await self.send(ErrorEvent(detail=NOT_HEARD))
        await self.send(StatusEvent(state="idle"))
        self._memory.release()

    async def _reply_to(self, text: str) -> None:
        try:
            turn = await self._conversation.respond(text)
        except ValueError as exc:
            await self.send(ErrorEvent(detail=str(exc)))
        except RateLimitedError:
            await self.send(ErrorEvent(detail=RATE_LIMITED))
        except LLMError:
            logger.exception("LLM provider failed")
            await self.send(ErrorEvent(detail="The companion is unavailable right now"))
        else:
            await self._send_turn(turn)

    async def _resolve(self, event: ResolveAction) -> None:
        try:
            resolution = await self._actions.resolve(event.id, confirm=event.confirm)
        except ActionNotFoundError:
            await self.send(ErrorEvent(detail="That action doesn't exist"))
        else:
            await self._send_resolution(resolution, speak=True)

    async def _send_turn(self, turn: Turn) -> None:
        if turn.resolution is not None:
            await self._send_resolution(turn.resolution, speak=False)
        await self.send(
            AssistantMessage(text=turn.reply, mode=turn.mode, teasing_allowed=turn.teasing_allowed)
        )
        if turn.proposal is not None:
            await self.send(
                PendingActionEvent(
                    id=turn.proposal.action_id,
                    kind=turn.proposal.kind,
                    summary=turn.proposal.summary,
                )
            )
        await self._speak(turn.reply)

    async def _send_resolution(self, resolution: Resolution, *, speak: bool) -> None:
        if speak:
            await self.send(
                AssistantMessage(
                    text=resolution.message,
                    mode=Mode.NORMAL,
                    teasing_allowed=self._conversation.teasing_allowed,
                )
            )
        await self.send(ActionResolvedEvent(id=resolution.action_id, status=resolution.status))
        if speak:
            await self._speak(resolution.message)

    async def _speak(self, text: str) -> None:
        if self._voice is None:
            return
        await self.send(StatusEvent(state="speaking"))
        started = time.perf_counter()
        first_audio = 0.0
        for clip in speech_clips(text):
            try:
                await self._ws.send_bytes(await self._voice.synthesize(clip))
            except Exception:
                logger.exception("Speech synthesis failed")
                return
            first_audio = first_audio or time.perf_counter() - started
        logger.info(
            "Voice started after %.2fs, finished after %.2fs",
            first_audio,
            time.perf_counter() - started,
        )


@router.websocket("/ws")
async def dev_text_channel(
    websocket: WebSocket, tz: str | None = None, speak: bool = False
) -> None:
    state = websocket.app.state
    user = await get_or_create_user(
        state.sessions, state.settings.dev_user_email, valid_timezone(tz)
    )
    await websocket.accept()
    actions = UserActions(state.actions, user.id, user.timezone)
    memory = UserMemory(
        state.memory,
        user.id,
        partial(extract_memories, state.llm) if state.settings.memory_extraction_enabled else None,
    )
    channel = _Channel(
        websocket,
        Conversation(state.llm, state.personality, actions, memory),
        actions,
        memory,
        state.listener,
        state.voice if speak else None,
        state.settings.max_audio_bytes,
    )
    disconnect = state.hub.connect(user.id, websocket.send_text)
    try:
        await state.reminders.dispatch_due()
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                await channel.handle_audio(message["bytes"])
            elif message.get("text") is not None:
                await channel.handle_text(message["text"])
    except WebSocketDisconnect:
        pass
    finally:
        disconnect()
