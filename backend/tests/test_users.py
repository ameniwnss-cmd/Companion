import pytest

from companion.db.session import SessionFactory
from companion.users import DEFAULT_TIMEZONE, get_or_create_user, valid_timezone


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Europe/Paris", "Europe/Paris"),
        ("Africa/Tunis", "Africa/Tunis"),
        ("Mars/Olympus_Mons", None),
        ("../../etc/passwd", None),
        ("", None),
        (None, None),
    ],
)
def test_valid_timezone(name: str | None, expected: str | None) -> None:
    assert valid_timezone(name) == expected


async def test_users_are_created_once_and_keep_their_timezone_updated(
    sessions: SessionFactory,
) -> None:
    first = await get_or_create_user(sessions, "ada@example.com", None)
    same = await get_or_create_user(sessions, "ada@example.com", "Europe/Paris")
    unchanged = await get_or_create_user(sessions, "ada@example.com", None)

    assert first.timezone == DEFAULT_TIMEZONE
    assert same.id == first.id
    assert same.timezone == "Europe/Paris"
    assert unchanged.timezone == "Europe/Paris"
