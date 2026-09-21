# Python 3.11 slim as the runtime base; uv is copied in from its official image
# pinned by version so that `uv sync --frozen` installs exactly uv.lock.
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080

WORKDIR /app

# Dependencies before sources, so editing application code does not invalidate
# the layer that holds the installed wheels.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src

# `/health/schema` compares the database's revision to the head this code ships, so
# the migration tree has to be in the image: without it the running code cannot name
# the revision it needs. Small, and nothing here runs at request time.
COPY alembic.ini ./
COPY migrations ./migrations

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8080

# exec keeps uvicorn as the process Cloud Run signals; no shell wrapper in between.
CMD ["sh", "-c", "exec uvicorn src.web.main:app --host 0.0.0.0 --port ${PORT}"]
