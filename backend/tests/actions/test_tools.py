import json

import pytest
from pydantic import BaseModel, ValidationError

from companion.actions.tools import (
    TOOLS,
    CreateReminderArgs,
    CreateTaskArgs,
    CreateWorkoutPlanArgs,
)


def test_three_tools_are_offered_with_json_schemas() -> None:
    by_name = {tool.name: tool for tool in TOOLS}

    assert set(by_name) == {"create_task", "create_reminder", "create_workout_plan"}
    assert by_name["create_reminder"].parameters["required"] == ["title", "when"]
    assert by_name["create_task"].parameters["required"] == ["title"]


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
        (CreateWorkoutPlanArgs, '{"name": "plan", "sessions": []}'),
        (
            CreateWorkoutPlanArgs,
            '{"name": "p", "sessions": [{"day": "funday", "focus": "legs", "minutes": 30}]}',
        ),
        (
            CreateWorkoutPlanArgs,
            '{"name": "p", "sessions": [{"day": "monday", "focus": "legs", "minutes": 500}]}',
        ),
    ],
)
def test_invalid_arguments_are_rejected(model: type[BaseModel], payload: str) -> None:
    with pytest.raises(ValidationError):
        model.model_validate_json(payload)


def test_tool_schemas_are_inlined_so_models_see_every_field() -> None:
    plan = next(tool for tool in TOOLS if tool.name == "create_workout_plan").parameters

    assert "$ref" not in json.dumps(plan)
    assert "$defs" not in plan
    session = plan["properties"]["sessions"]["items"]
    assert set(session["required"]) == {"day", "focus", "minutes"}
    assert session["additionalProperties"] is False
