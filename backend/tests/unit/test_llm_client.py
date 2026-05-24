"""Unit tests for the LLM client (mocked with respx).

The openai SDK owns retry policy; these tests just verify that our
configuration flows through correctly — happy path, 4xx surfacing
immediately, and SDK exponential-backoff retries firing on 5xx.
"""
from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from openai import AsyncOpenAI, BadRequestError

from app.api.main import app
from app.llm.client import LLM


BASE = "http://fake-llm/v1"
CHAT_URL = f"{BASE}/chat/completions"


def _llm(max_retries: int = 2) -> LLM:
    client = AsyncOpenAI(api_key="test", base_url=BASE, max_retries=max_retries)
    return LLM(client=client, model="test-model", provider="openrouter")


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
async def test_sdk_retries_5xx_then_succeeds() -> None:
    route = respx.post(CHAT_URL).mock(
        side_effect=[
            httpx.Response(503, text="busy"),
            httpx.Response(200, json=_completion_body("recovered")),
        ]
    )

    completion = await _llm(max_retries=2).chat(
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
        await _llm(max_retries=2).chat([{"role": "user", "content": "hi"}])

    assert route.call_count == 1  # 4xx must not retry


@pytest.mark.asyncio
@respx.mock
async def test_max_retries_zero_means_one_attempt() -> None:
    route = respx.post(CHAT_URL).mock(
        return_value=httpx.Response(503, text="busy")
    )

    with pytest.raises(Exception):  # APIStatusError / InternalServerError
        await _llm(max_retries=0).chat([{"role": "user", "content": "hi"}])

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_ok_outcome_recorded_in_metrics() -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(200, json=_completion_body("hi"))
    )

    await _llm(max_retries=0).chat([{"role": "user", "content": "hi"}])

    with TestClient(app) as http:
        body = http.get("/metrics").text

    assert "llm_call_duration_seconds_count" in body
    assert 'provider="openrouter"' in body
    assert 'outcome="ok"' in body


@pytest.mark.asyncio
@respx.mock
async def test_error_outcome_recorded_in_metrics() -> None:
    respx.post(CHAT_URL).mock(
        return_value=httpx.Response(
            400, json={"error": {"message": "bad request"}}
        )
    )

    with pytest.raises(BadRequestError):
        await _llm(max_retries=0).chat([{"role": "user", "content": "hi"}])

    with TestClient(app) as http:
        body = http.get("/metrics").text

    assert 'llm_call_duration_seconds_count{outcome="error"' in body
    assert 'provider="openrouter"' in body
