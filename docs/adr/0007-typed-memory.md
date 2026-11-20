# 0007. Typed long-term memory, learned in the background

- Status: Accepted

## Context

A coach is only useful if it remembers your goals, habits and what is going on in your life. A
memory that writes down everything is a privacy problem, and a memory the user cannot see or
correct is a trust problem. Reply latency also matters in a voice app.

## Decision

- **Typed memories.** Each one is a short third-person sentence with one of five kinds:
  preference, goal, commitment, habit or recent context. Recent context expires after 7 days.
- **Learned after the reply, in the background.** After each turn, a JSON-mode call extracts at
  most 3 candidates. Short answers ("ok", "yes please") are skipped. The reply is never delayed.
- **Sensitive topics are never stored.** The extraction prompt forbids health, body, mental
  health, religion, money and similar topics. Code then re-checks every candidate with the same
  keyword rules as the safety router, and nothing is learned from a crisis turn.
- **Recall by meaning.** Memories are embedded with a small local model (Ollama `all-minilm`,
  384 dimensions) and stored in Postgres with pgvector and an HNSW index. The six most relevant
  memories are added to the prompt each turn.
- **No duplicates.** A new fact within a small cosine distance of an existing one updates it
  instead of adding another row.
- **The user is in control.** Memories can be listed, edited (re-embedded on change) and
  deleted, one by one or all at once. Every query is scoped to the user, and cross-user tests
  prove it.

## Consequences

- An extra model call per meaningful turn. It runs in the background but counts against the
  provider's rate limits.
- Recall depends on embedding quality. A small model is good enough for short sentences. The
  embedder is behind an interface and can be swapped.
- If extraction or recall fails, the conversation carries on without memory, and the failure is
  logged.
