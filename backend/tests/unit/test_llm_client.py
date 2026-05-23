"""Unit tests for the LLM client (mocked with respx).

Mirrors the structure of test_fhir_client.py: a real `LLM` is constructed
against a fake base URL and HTTP responses are stubbed at the httpx layer.
"""
from __future__ import annotations

import httpx
import pytest
import respx
from openai import AsyncOpenAI, BadRequestError

from app.llm.client import LLM


BASE = "http://fake-llm/v1"
CHAT_URL = f"{BASE}/chat/completions"


def _llm(max_attempts: int = 3) -> LLM:
    client = AsyncOpenAI(api_key="test", base_url=BASE)
    return LLM(
        client=client,
        model="test-model",
        provider="openrouter",
        max_attempts=max_attempts,
        # Keep test runtime small.
        retry_base_delay=0.01,
        retry_max_delay=0.05,
    )


def _completion_body(content: str = "ok") -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


@pytest.mark.asyncio
@respx.mock
async def test_chat_returns_completion_on_success() -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_completion_body("hello"))
    )

    completion = await _llm().chat([{"role": "user", "content": "hi"}])

    assert completion.choices[0].message.content == "hello"


@pytest.mark.asyncio
@respx.mock
async def test_5xx_retries_then_succeeds() -> None:
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(503, text="busy"),
            httpx.Response(200, json=_completion_body("recovered")),
        ]
    )

    completion = await _llm(max_attempts=3).chat(
        [{"role": "user", "content": "hi"}]
    )

    assert completion.choices[0].message.content == "recovered"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_4xx_raises_without_retry() -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            400, json={"error": {"message": "bad request"}}
        )
    )

    with pytest.raises(BadRequestError):
        await _llm(max_attempts=3).chat([{"role": "user", "content": "hi"}])

    assert route.call_count == 1  # 4xx must not retry
