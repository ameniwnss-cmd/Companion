import uuid

from companion.realtime.hub import ConnectionHub


class Inbox:
    def __init__(self, *, broken: bool = False) -> None:
        self.messages: list[str] = []
        self.broken = broken

    async def __call__(self, message: str) -> None:
        if self.broken:
            raise ConnectionError("socket closed")
        self.messages.append(message)


async def test_messages_reach_every_connection_of_that_user_only() -> None:
    hub = ConnectionHub()
    alice, bob = uuid.uuid4(), uuid.uuid4()
    phone, laptop, bobs = Inbox(), Inbox(), Inbox()
    hub.connect(alice, phone)
    hub.connect(alice, laptop)
    hub.connect(bob, bobs)

    assert await hub.send(alice, "hi")
    assert phone.messages == laptop.messages == ["hi"]
    assert bobs.messages == []


async def test_disconnecting_removes_the_user_when_no_connections_remain() -> None:
    hub = ConnectionHub()
    user = uuid.uuid4()
    disconnect = hub.connect(user, Inbox())

    assert hub.connected_users() == {user}
    disconnect()
    disconnect()
    assert hub.connected_users() == set()
    assert not await hub.send(user, "anyone?")


async def test_a_broken_connection_is_dropped() -> None:
    hub = ConnectionHub()
    user = uuid.uuid4()
    healthy, broken = Inbox(), Inbox(broken=True)
    hub.connect(user, healthy)
    hub.connect(user, broken)

    assert await hub.send(user, "first")
    healthy.broken = True
    assert not await hub.send(user, "second")
