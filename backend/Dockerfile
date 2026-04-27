# syntax=docker/dockerfile:1.7
# ── Build stage (Docker Hardened Image, dev variant) ──────────────────
FROM dhi.io/python:3.13-debian13-dev AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.10.0 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/root/.cache/uv

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# ── Runtime stage (DHI distroless: no shell, no pkg manager, non-root) ─
FROM dhi.io/python:3.13-debian13

WORKDIR /app

COPY --from=builder --chown=nonroot:nonroot /app /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

EXPOSE 8000
ENTRYPOINT ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info"]
