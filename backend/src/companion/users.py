from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from companion.db.models import User
from companion.db.session import SessionFactory

DEFAULT_TIMEZONE = "UTC"


def valid_timezone(name: str | None) -> str | None:
    if not name:
        return None
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return name


async def get_or_create_user(sessions: SessionFactory, email: str, timezone: str | None) -> User:
    async with sessions() as session, session.begin():
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, timezone=timezone or DEFAULT_TIMEZONE)
            session.add(user)
        elif timezone and user.timezone != timezone:
            user.timezone = timezone
    return user
