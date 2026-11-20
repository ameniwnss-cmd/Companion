# 0004. Actions are proposed, then confirmed by the user

- Status: Accepted

## Context

The companion creates tasks, reminders and workout plans through LLM tool calls. Speech
recognition mishears, models misread intent, and in the spike a small model sometimes emitted
the same tool call twice. Saving straight from a tool call would leave wrong data behind.

## Decision

The model never writes to the database. A tool call creates a **pending action**: validated with
Pydantic, deduplicated, and stored with status `pending`. The companion reads it back ("Reminder
to call your mom tomorrow at 6 pm, want me to save it?") and the UI shows a confirmation card.
Only an explicit yes, spoken or tapped, executes it. No, a timeout, or a new request cancels it.

One request can hold several items ("add milk, eggs and call the bank at 5"). Tasks and reminders
share one tool that takes lists, because the hosted model makes a single tool call per reply and
would otherwise drop everything after the first item. The valid, distinct items become one
**batch** of pending actions that is read back and confirmed with a single yes. Items with
unclear details are left out and the companion asks for them again.

A confirmed batch can be **undone** for ten minutes, by voice ("undo that") or a button. Undo
deletes exactly the records that batch created, which each pending action remembers. This keeps
hands-free use quick without letting the model save anything on its own.

Spoken answers are matched by code, not by the model. The first meaningful word decides
("Yes, do it", "Yeah, David" from a mishearing, "no thanks"), and words that change the request
("yes but at 7", "ok and also...") turn it into a new request instead.

Times are passed through as the user said them ("next Tuesday morning") and converted to dates by
deterministic code, because language models are unreliable at date arithmetic.

## Consequences

- Every write is traceable to a user confirmation, which also makes the flow easy to test end to
  end.
- One extra conversational turn per action, which is acceptable for a voice assistant and matches
  how a person would double-check.
- The pending-action lifecycle (create, confirm, cancel, expire) needs its own state machine and
  tests.
