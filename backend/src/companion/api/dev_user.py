import uuid
from typing import Annotated

from fastapi import Depends, Request

from companion.users import get_or_create_user


async def dev_user_id(request: Request) -> uuid.UUID:
    state = request.app.state
    user = await get_or_create_user(state.sessions, state.settings.dev_user_email, None)
    return user.id


DevUserId = Annotated[uuid.UUID, Depends(dev_user_id)]
