# syntax=docker/dockerfile:1.7

# Base image via CN mirror for faster pulls in mainland China.
# Remove the swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/ prefix if you are outside CN.
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# Build tools needed by some Python packages (asyncpg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, reproducible dependency resolution from uv.lock.
# Installed via pip (from PyPI) to avoid pulling the ghcr.io/uv image,
# which is not mirrored by the CN registry.
RUN pip install --no-cache-dir uv==0.5.18

WORKDIR /srv

# Install dependencies first (better layer caching)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# -------------------------------------------------------------------
# Runtime stage: slim image without build toolchain
# -------------------------------------------------------------------
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/srv/.venv/bin:$PATH"

# Runtime library for asyncpg (libpq) and curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Copy the pre-built virtualenv from the builder stage
COPY --from=builder /srv/.venv /srv/.venv

# Copy application source (backend lives under app/, frontend under frontend/,
# sample logs under test_logs/)
COPY app ./app
COPY frontend ./frontend
COPY test_logs ./test_logs

EXPOSE 8000

# Run via uvicorn bound to all interfaces so the container port is reachable.
# Entry point is the FastAPI `app` object inside app/main.py.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
