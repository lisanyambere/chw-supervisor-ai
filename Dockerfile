# Repo-level image for Project Silver — builds the backend so pytest can run
# against any base_commit. Frontend is intentionally not built here; tasks
# target backend code paths.

FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# git is required at runtime — Silver does `git reset --hard <base_commit>`
# before each task. python:slim does not ship it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

# Local-path install (exempt from the pip pin rule). Pulls runtime + dev deps
# (pytest, pytest-asyncio, respx) from backend/pyproject.toml.
RUN pip install -e "./backend[dev]"

WORKDIR /app/backend

CMD ["bash"]
