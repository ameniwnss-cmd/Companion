from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from companion.db.models import ActionKind
from companion.llm import ToolSpec

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateTaskArgs(_Args):
    title: ShortText = Field(description="What needs doing, in a few words.")
    due: str | None = Field(
        default=None,
        description="When it is due, exactly as the user said it, e.g. 'Friday'. Omit if not said.",
    )


class CreateReminderArgs(_Args):
    title: ShortText = Field(description="What to remind the user about, e.g. 'call mom'.")
    when: str = Field(
        min_length=1,
        description="When to remind them, exactly as the user said it, e.g. 'tomorrow at 6pm'.",
    )


class Weekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


class WorkoutSession(_Args):
    day: Weekday = Field(description="Day of the week, lowercase, e.g. 'monday'.")
    focus: Annotated[str, Field(min_length=1, max_length=60)] = Field(
        description="What the session trains, e.g. 'upper body' or 'easy run'."
    )
    minutes: int = Field(ge=10, le=180, description="How long the session lasts, in minutes.")


class CreateWorkoutPlanArgs(_Args):
    name: ShortText = Field(description="A short name for the plan.")
    sessions: list[WorkoutSession] = Field(min_length=1, max_length=7)


ARGUMENTS: dict[ActionKind, type[_Args]] = {
    ActionKind.TASK: CreateTaskArgs,
    ActionKind.REMINDER: CreateReminderArgs,
    ActionKind.WORKOUT_PLAN: CreateWorkoutPlanArgs,
}

TOOL_NAMES: dict[str, ActionKind] = {
    "create_task": ActionKind.TASK,
    "create_reminder": ActionKind.REMINDER,
    "create_workout_plan": ActionKind.WORKOUT_PLAN,
}

_DESCRIPTIONS = {
    ActionKind.TASK: "Add something to the user's to-do list.",
    ActionKind.REMINDER: "Remind the user about something at a specific time.",
    ActionKind.WORKOUT_PLAN: "Create a weekly workout plan the user asked for.",
}


def inline_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(definitions[node["$ref"].rsplit("/", 1)[-1]])
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    resolved: dict[str, Any] = resolve(schema)
    return resolved


TOOLS: tuple[ToolSpec, ...] = tuple(
    ToolSpec(name=name, description=_DESCRIPTIONS[kind], parameters=inline_schema(ARGUMENTS[kind]))
    for name, kind in TOOL_NAMES.items()
)
