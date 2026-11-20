# 0006. Reminders are delivered by an in-process polling loop

- Status: Accepted

## Context

Confirmed reminders must reach the user at the right time, by voice or a notification, while
they have the app open. The stack excludes Redis and task queues, and the app runs as a single
backend process for now.

## Decision

A background task started with the FastAPI app polls Postgres every 30 seconds. It selects due,
undelivered reminders that belong to users with an open connection, sends each one through the
in-memory connection hub, and marks it delivered only if a send succeeded. The query uses
`FOR UPDATE SKIP LOCKED`, so a second backend instance would never deliver the same reminder
twice. When a user connects, any overdue reminders are delivered straight away.

The client keeps one connection for the whole app, so reminders arrive on every page. A due
reminder plays a short chime, the companion says it out loud, and a system notification pops up
when the app is in the background and the user has allowed it. The notice is sent straight away,
but the spoken part waits for the current conversational turn to finish, so the companion never
talks over the user or itself. The reminder is added to the conversation history, so the next
reply knows it was said. A repeating reminder is moved to its next day instead of being marked
delivered.

Times are parsed deterministically by our own small parser (`actions/when.py`), not by the
language model, and stored in UTC. They are interpreted in the user's timezone, which the client
sends when it connects.

## Consequences

- No extra infrastructure: one process, one database.
- Delivery can be up to 30 seconds late. That is fine for reminders, and the interval is a
  setting.
- Reminders only reach users who have the app open. Push notifications to closed apps would need
  a push service. That is out of scope for v1, and is the trigger to revisit this decision.
- The in-memory hub works for one backend instance. Several instances would need a shared
  channel, for example Postgres `LISTEN/NOTIFY`, which still avoids adding Redis.
