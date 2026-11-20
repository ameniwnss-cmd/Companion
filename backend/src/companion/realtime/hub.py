import logging
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

Sender = Callable[[str], Awaitable[None]]


class ConnectionHub:
    def __init__(self) -> None:
        self._senders: defaultdict[uuid.UUID, set[Sender]] = defaultdict(set)

    def connect(self, user_id: uuid.UUID, sender: Sender) -> Callable[[], None]:
        self._senders[user_id].add(sender)

        def disconnect() -> None:
            senders = self._senders.get(user_id)
            if senders is not None:
                senders.discard(sender)
                if not senders:
                    del self._senders[user_id]

        return disconnect

    def connected_users(self) -> set[uuid.UUID]:
        return set(self._senders)

    async def send(self, user_id: uuid.UUID, message: str) -> bool:
        delivered = False
        for sender in list(self._senders.get(user_id, ())):
            try:
                await sender(message)
                delivered = True
            except Exception:
                logger.warning("Dropping a connection that failed to receive a message")
                self._senders[user_id].discard(sender)
        return delivered
