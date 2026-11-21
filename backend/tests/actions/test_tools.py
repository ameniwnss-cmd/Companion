import json

import pytest
from pydantic import BaseModel, ValidationError

from companion.actions.tools import (
    COMPLETE_TASKS,
    MAX_ITEMS_PER_LIST,
    TASKS_AND_REMINDERS,
    TOOLS,
    AddTasksAndRemindersArgs,
    CompleteTaskArgs,
    CompleteTasksArgs,
    CreateReminderArgs,
    CreateTaskArgs,
    CreateWeeklyPlanArgs,
    UnknownToolError,
    requested_items,
)
from companion.llm import ToolCall


def test_three_tools_are_offered_with_json_schemas() -> None:
    by_name = {tool.name: tool for tool in TOOLS}

    assert set(by_name) == {"add_tasks_and_reminders", "create_weekly_plan", "complete_tasks"}
    assert by_name["complete_tasks"].parameters["required"] == ["titles"]
    lists = by_name["add_tasks_and_reminders"].parameters["properties"]
    assert lists["reminders"]["items"]["required"] == ["title", "when"]
    assert lists["tasks"]["items"]["required"] == ["title"]


def test_one_call_lists_every_task_and_reminder() -> None:
    arguments = json.dumps(
        {
            "tasks": [{"title": "milk"}, {"title": "bank"}],
            "reminders": [{"title": "a", "when": "6"}],
        }
    )

    items = requested_items(ToolCall(TASKS_AND_REMINDERS, arguments))

    assert [type(item).__name__ for item in items] == [
        "CreateTaskArgs",
        "CreateTaskArgs",
        "CreateReminderArgs",
    ]


def test_one_call_ticks_off_every_finished_task() -> None:
    arguments = json.dumps({"titles": ["apply for jobs", " buy milk "]})

    items = requested_items(ToolCall(COMPLETE_TASKS, arguments))

    assert items == [CompleteTaskArgs(title="apply for jobs"), CompleteTaskArgs(title="buy milk")]


def test_an_unknown_tool_is_refused() -> None:
    with pytest.raises(UnknownToolError):
        requested_items(ToolCall("drop_tables", "{}"))


def test_arguments_are_trimmed() -> None:
    args = CreateReminderArgs.model_validate_json('{"title": "  call mom ", "when": "at 6"}')

    assert args.title == "call mom"


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (CreateReminderArgs, '{"title": "call mom"}'),
        (CreateReminderArgs, '{"title": "", "when": "at 6"}'),
        (CreateReminderArgs, '{"title": "x", "when": "at 6", "priority": "high"}'),
        (CreateTaskArgs, '{"title": "' + "x" * 201 + '"}'),
        (
            AddTasksAndRemindersArgs,
            json.dumps({"tasks": [{"title": "x"}] * (MAX_ITEMS_PER_LIST + 1)}),
        ),
        (CreateWeeklyPlanArgs, '{"name": "plan", "days": []}'),
        (CompleteTasksArgs, '{"titles": []}'),
        (CompleteTasksArgs, '{"titles": [""]}'),
        (CompleteTasksArgs, json.dumps({"titles": ["x"] * (MAX_ITEMS_PER_LIST + 1)})),
        (
            CreateWeeklyPlanArgs,
            '{"name": "p", "days": [{"day": "funday", "activity": "legs", "minutes": 30}]}',
        ),
        (
            CreateWeeklyPlanArgs,
            '{"name": "p", "days": [{"day": "monday", "activity": "legs", "minutes": 900}]}',
        ),
    ],
)
def test_invalid_arguments_are_rejected(model: type[BaseModel], payload: str) -> None:
    with pytest.raises(ValidationError):
        model.model_validate_json(payload)


def test_tool_schemas_are_inlined_so_models_see_every_field() -> None:
    plan = next(tool for tool in TOOLS if tool.name == "create_weekly_plan").parameters

    assert "$ref" not in json.dumps(plan)
    assert "$defs" not in plan
    session = plan["properties"]["days"]["items"]
    assert set(session["required"]) == {"day", "activity"}
    assert session["additionalProperties"] is False


def test_repeat_days_must_be_real_weekdays() -> None:
    with pytest.raises(ValidationError):
        CreateTaskArgs.model_validate_json('{"title": "x", "repeat": ["someday"]}')
    with pytest.raises(ValidationError):
        CreateReminderArgs.model_validate_json('{"title": "x", "when": "9pm", "repeat": []}')
