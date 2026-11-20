# syntax=docker/dockerfile:1

# ---- build: resolve dependencies from the lockfile into a virtualenv
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# Dependencies first, so this layer is cached until uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime: only the virtualenv and the code, running as a non-root user
FROM python:3.13-slim AS runtime
RUN useradd --create-home --uid 10001 companion
WORKDIR /app
COPY --from=build --chown=companion:companion /app /app
COPY --chown=companion:companion config ./config

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
USER companion
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "companion.main:app", "--host", "0.0.0.0", "--port", "8000"]
