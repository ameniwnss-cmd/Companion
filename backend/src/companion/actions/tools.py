from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from companion.db.models import ActionKind
from companion.llm import ToolCall, ToolSpec

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Weekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


RepeatDays = Annotated[list[Weekday], Field(min_length=1, max_length=7)]

REPEAT_HELP = (
    "Only for something that repeats: the days it happens, lowercase, e.g. all seven days for "
    "'every day' or monday to friday for 'every weekday'. Omit for a one-off."
)


class CreateTaskArgs(_Args):
    title: ShortText = Field(description="What needs doing, in a few words.")
    due: str | None = Field(
        default=None,
        description=(
            "For a one-off task, when it is due, exactly as the user said it, e.g. 'Friday'. "
            "Omit if not said or if the task repeats."
        ),
    )
    repeat: RepeatDays | None = Field(default=None, description=REPEAT_HELP)
    at: str | None = Field(
        default=None,
        description="For a repeating task, the time of day as the user said it, e.g. '9am'.",
    )


class CreateReminderArgs(_Args):
    title: ShortText = Field(description="What to remind the user about, e.g. 'call mom'.")
    when: str = Field(
        min_length=1,
        description=(
            "When to remind them, exactly as the user said it, e.g. 'tomorrow at 6pm'. "
            "For a repeating reminder, just the time of day, e.g. '9pm'."
        ),
    )
    repeat: RepeatDays | None = Field(default=None, description=REPEAT_HELP)


class PlanDay(_Args):
    day: Weekday = Field(description="Day of the week, lowercase, e.g. 'monday'.")
    activity: Annotated[str, Field(min_length=1, max_length=80)] = Field(
        description="What the user does that day, e.g. 'polish the portfolio' or 'easy run'."
    )
    minutes: int | None = Field(
        default=None, ge=5, le=600, description="How long it takes, in minutes, if known."
    )


class CreateWeeklyPlanArgs(_Args):
    name: ShortText = Field(description="A short name for the plan.")
    days: list[PlanDay] = Field(min_length=1, max_length=14)


MAX_ITEMS_PER_LIST = 10


class AddTasksAndRemindersArgs(_Args):
    tasks: list[CreateTaskArgs] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_PER_LIST,
        description="Every to-do item the user asked for in this message, one entry each.",
    )
    reminders: list[CreateReminderArgs] = Field(
        default_factory=list,
        max_length=MAX_ITEMS_PER_LIST,
        description="Every reminder the user asked for in this message, one entry each.",
    )


class CompleteTaskArgs(_Args):
    title: ShortText


class CompleteTasksArgs(_Args):
    titles: list[ShortText] = Field(
        min_length=1,
        max_length=MAX_ITEMS_PER_LIST,
        description=(
            "The tasks the user says they finished, each copied exactly from their open tasks."
        ),
    )


TASKS_AND_REMINDERS = "add_tasks_and_reminders"
WEEKLY_PLAN = "create_weekly_plan"
COMPLETE_TASKS = "complete_tasks"

ItemArgs = CreateTaskArgs | CreateReminderArgs | CreateWeeklyPlanArgs | CompleteTaskArgs

KINDS: dict[type[ItemArgs], ActionKind] = {
    CreateTaskArgs: ActionKind.TASK,
    CreateReminderArgs: ActionKind.REMINDER,
    CreateWeeklyPlanArgs: ActionKind.WEEKLY_PLAN,
    CompleteTaskArgs: ActionKind.COMPLETE_TASK,
}


class UnknownToolError(LookupError):
    pass


def requested_items(call: ToolCall) -> list[ItemArgs]:
    if call.name == TASKS_AND_REMINDERS:
        args = AddTasksAndRemindersArgs.model_validate_json(call.arguments)
        return [*args.tasks, *args.reminders]
    if call.name == WEEKLY_PLAN:
        return [CreateWeeklyPlanArgs.model_validate_json(call.arguments)]
    if call.name == COMPLETE_TASKS:
        finished = CompleteTasksArgs.model_validate_json(call.arguments)
        return [CompleteTaskArgs(title=title) for title in finished.titles]
    raise UnknownToolError(call.name)


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


TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name=TASKS_AND_REMINDERS,
        description=(
            "Add to-do items and set reminders for the user. Put every task and every reminder "
            "from their message into this one call."
        ),
        parameters=inline_schema(AddTasksAndRemindersArgs),
    ),
    ToolSpec(
        name=WEEKLY_PLAN,
        description=(
            "Create a weekly plan where each day has its own activity, e.g. a workout schedule "
            "or 'Monday portfolio, Tuesday two applications'. For the same thing repeated on "
            "several days, use a repeating task instead."
        ),
        parameters=inline_schema(CreateWeeklyPlanArgs),
    ),
    ToolSpec(
        name=COMPLETE_TASKS,
        description=(
            "Tick off tasks the user says they have finished. Put every finished task from "
            "their message into this one call, using the exact titles from their open tasks."
        ),
        parameters=inline_schema(CompleteTasksArgs),
    ),
)
