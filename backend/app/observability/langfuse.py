"""Langfuse client singleton.

Disabled (returns None) when LANGFUSE_PUBLIC_KEY is empty so local dev without
a Langfuse instance just no-ops.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core import get_logger, get_settings

log = get_logger(__name__)


@lru_cache(maxsize=1)
def get_langfuse() -> Any | None:
    s = get_settings()
    if not s.langfuse_public_key or not s.langfuse_secret_key:
        log.info("langfuse.disabled", reason="keys not set")
        return None
    try:
        from langfuse import Langfuse
    except ImportError:
        log.warning("langfuse.import_failed")
        return None

    client = Langfuse(
        public_key=s.langfuse_public_key,
        secret_key=s.langfuse_secret_key,
        host=s.langfuse_host,
    )
    log.info("langfuse.enabled", host=s.langfuse_host)
    return client


async def aflush() -> None:
    """Best-effort flush of pending events on shutdown."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.flush()
    except Exception as e:  # noqa: BLE001
        log.warning("langfuse.flush_failed", error=str(e))
