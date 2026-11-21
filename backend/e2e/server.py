import asyncio
import json
import os
from collections.abc import Sequence

import uvicorn

from companion.config import Environment, Settings
from companion.db.setup import create_database_if_missing, empty_database, migrate
from companion.llm import ChatMessage, LLMReply, Role, ToolCall
from companion.llm.fake import FakeLLM
from companion.main import create_app
from companion.speech.stt import FakeSpeechToText

DATABASE_URL = os.environ.get(
    "E2E_DATABASE_URL", "postgresql+asyncpg://companion:companion@localhost:5433/companion_e2e"
)
PORT = int(os.environ.get("E2E_BACKEND_PORT", "8100"))
FRONTEND = os.environ.get("E2E_FRONTEND_ORIGIN", "http://localhost:4300")

HEARD = "Remind me to stretch tomorrow at 9am."
STRETCH = ToolCall(
    "add_tasks_and_reminders",
    json.dumps({"reminders": [{"title": "stretch", "when": "tomorrow at 9am"}]}),
)


def scripted(messages: Sequence[ChatMessage], json_mode: bool) -> str | LLMReply:
    if json_mode:
        return '{"mode": "normal"}'
    said = next(m.content for m in reversed(messages) if m.role is Role.USER)
    if "remind me" in said.lower():
        return LLMReply(text="", tool_calls=(STRETCH,))
    return "Look at you, actually doing it."


def main() -> None:
    asyncio.run(create_database_if_missing(DATABASE_URL))
    migrate(DATABASE_URL)
    asyncio.run(empty_database(DATABASE_URL))
    settings = Settings(
        environment=Environment.TEST,
        database_url=DATABASE_URL,
        dev_text_channel=True,
        cors_origins=[FRONTEND],
        memory_extraction_enabled=False,
        reminder_loop_enabled=False,
        _env_file=None,
    )
    app = create_app(settings, llm=FakeLLM(responder=scripted), listener=FakeSpeechToText(HEARD))
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
