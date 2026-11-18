"""Unit tests for the LLM client.

The openai SDK owns retry policy; these tests just verify that our
configuration flows through correctly — happy path, 4xx surfacing
immediately, and SDK exponential-backoff retries firing on 5xx.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx2
import pytest
from fastapi.testclient import TestClient
from openai import APIStatusError, AsyncOpenAI, BadRequestError

from app.api.main import app
from app.llm.client import LLM

BASE = "http://fake-llm/v1"

# openai>=3 sends requests through httpx2, which respx cannot intercept, so the
# SDK is given an httpx2 client with a mock transport instead.


class FakeServer:
    """Replies to chat-completion POSTs in order and records each call."""

    def __init__(self, *responses: httpx2.Response) -> None:
        self.responses = list(responses)
        self.call_count = 0

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == "/v1/chat/completions"
        self.call_count += 1
        # Repeat the last response once the script runs out.
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


Handler = Callable[[httpx2.Request], httpx2.Response]


def _llm(server: Handler, max_retries: int = 2) -> LLM:
    client = AsyncOpenAI(
        api_key="test",
        base_url=BASE,
        max_retries=max_retries,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(server)),
    )
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
async def test_chat_returns_completion_on_success() -> None:
    server = FakeServer(httpx2.Response(200, json=_completion_body("hello")))

    completion = await _llm(server).chat([{"role": "user", "content": "hi"}])

    assert completion.choices[0].message.content == "hello"


@pytest.mark.asyncio
async def test_sdk_retries_5xx_then_succeeds() -> None:
    server = FakeServer(
        httpx2.Response(503, text="busy"),
        httpx2.Response(200, json=_completion_body("recovered")),
    )

    completion = await _llm(server, max_retries=2).chat(
        [{"role": "user", "content": "hi"}]
    )

    assert completion.choices[0].message.content == "recovered"
    assert server.call_count == 2


@pytest.mark.asyncio
async def test_4xx_raises_without_retry() -> None:
    server = FakeServer(
        httpx2.Response(400, json={"error": {"message": "bad request"}})
    )

    with pytest.raises(BadRequestError):
        await _llm(server, max_retries=2).chat([{"role": "user", "content": "hi"}])

    assert server.call_count == 1  # 4xx must not retry


@pytest.mark.asyncio
async def test_max_retries_zero_means_one_attempt() -> None:
    server = FakeServer(httpx2.Response(503, text="busy"))

    with pytest.raises(APIStatusError):
        await _llm(server, max_retries=0).chat([{"role": "user", "content": "hi"}])

    assert server.call_count == 1


@pytest.mark.asyncio
async def test_ok_outcome_recorded_in_metrics() -> None:
    server = FakeServer(httpx2.Response(200, json=_completion_body("hi")))

    await _llm(server, max_retries=0).chat([{"role": "user", "content": "hi"}])

    with TestClient(app) as http:
        body = http.get("/metrics").text

    assert "llm_call_duration_seconds_count" in body
    assert 'provider="openrouter"' in body
    assert 'outcome="ok"' in body


@pytest.mark.asyncio
async def test_error_outcome_recorded_in_metrics() -> None:
    server = FakeServer(
        httpx2.Response(400, json={"error": {"message": "bad request"}})
    )

    with pytest.raises(BadRequestError):
        await _llm(server, max_retries=0).chat([{"role": "user", "content": "hi"}])

    with TestClient(app) as http:
        body = http.get("/metrics").text

    assert 'llm_call_duration_seconds_count{outcome="error"' in body
    assert 'provider="openrouter"' in body
