# 0001. Monorepo with a separate frontend and backend

- Status: Accepted

## Context

The product has an Angular client and a Python API that change together: the WebSocket message
protocol, for example, is defined on one side and consumed on the other. One developer maintains
both.

## Decision

One repository with `frontend/`, `backend/` and `docs/` at the top level, each with its own
toolchain (npm for the frontend, uv for the backend). A single CI workflow runs independent jobs
for each, and Docker Compose starts the stack from the root.

## Consequences

- A protocol change and both of its sides land in one commit and one review.
- Each half stays independently buildable and testable; neither imports the other's code.
- CI runs both jobs on every push. The jobs are fast and run in parallel, so this is acceptable
  now; path filters can be added if it stops being so.
