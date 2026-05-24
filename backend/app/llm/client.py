"""LLM client factory.

The openai SDK works for both OpenRouter (OpenAI-compatible base URL) and Azure
OpenAI. Switching providers is just `LLM_PROVIDER=openrouter|azure` in env.

Callers should use `get_llm()` to obtain a `LLM` wrapper exposing
`async chat(messages, tools=None, **kwargs)` returning the first choice.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core import get_logger, get_settings

log = get_logger(__name__)

# Sentinel so callers can pass `temperature=None` to mean "omit", while a
# missing argument means "use the provider default".
_UNSET: Any = object()


# Retry transport-level failures and 5xx server errors. 4xx (including 429)
# is intentionally not retried here; 429 with a Retry-After header is a known
# follow-up.
def _should_retry_llm(exc: BaseException) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        status = getattr(exc, "status_code", None)
        return status is not None and status >= 500
    return False


@dataclass
class LLM:
    """Provider-agnostic chat helper."""

    client: AsyncOpenAI
    model: str  # OpenRouter model id or Azure deployment name
    provider: str
    # GPT-5 family on Azure rejects any non-default temperature.
    # Set to None to omit the field entirely from the request.
    default_temperature: float | None = 0.2
    # Retry knobs — tests construct an LLM directly with tighter values.
    max_attempts: int = 3
    retry_base_delay: float = 0.5
    retry_max_delay: float = 4.0

    async def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] = "auto",
        temperature: float | None = _UNSET,  # type: ignore[assignment]
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> ChatCompletion:
        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        # If caller did not pass temperature, fall back to the per-provider
        # default (which may be None, meaning "omit").
        effective_temp = (
            self.default_temperature if temperature is _UNSET else temperature
        )
        if effective_temp is not None:
            params["temperature"] = effective_temp
        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
        if max_tokens is not None:
            params["max_tokens"] = max_tokens
        params.update(kwargs)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential(
                multiplier=self.retry_base_delay,
                min=self.retry_base_delay,
                max=self.retry_max_delay,
            ),
            retry=retry_if_exception(_should_retry_llm),
            reraise=True,
        ):
            with attempt:
                return await self.client.chat.completions.create(**params)
        # Unreachable — reraise=True surfaces the underlying exception.
        raise RuntimeError("llm retry exhausted")


def _build_openrouter() -> LLM:
    s = get_settings()
    if not s.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    client = AsyncOpenAI(
        api_key=s.openrouter_api_key,
        base_url=s.openrouter_base_url,
        # Tenacity owns the retry policy. The openai SDK defaults to
        # max_retries=2, which silently retries transient 5xx responses
        # BEFORE our tenacity wrapper observes them — making the wrapper
        # effectively dead code under typical failure modes.
        max_retries=0,
        # OpenRouter recommends these headers for attribution / rate-limit tier.
        default_headers={
            "HTTP-Referer": "https://github.com/lisanyambere/chw-supervisor-ai",
            "X-Title": "Community Health AI Assistant",
        },
    )
    return LLM(
        client=client,
        model=s.openrouter_model,
        provider="openrouter",
        max_attempts=s.llm_max_attempts,
        retry_base_delay=s.llm_retry_base_delay,
        retry_max_delay=s.llm_retry_max_delay,
    )


def _build_azure() -> LLM:
    """Build an Azure OpenAI client using the v1 OpenAI-compatible endpoint.

    Azure exposes `https://<resource>.cognitiveservices.azure.com/openai/v1/`
    which is fully OpenAI-compatible — so we use the plain AsyncOpenAI client
    with that base_url and pass the deployment name as `model`. No
    `api_version` is required for this surface.
    """
    s = get_settings()
    missing = [
        name
        for name, value in {
            "AZURE_OPENAI_API_KEY": s.azure_openai_api_key,
            "AZURE_OPENAI_ENDPOINT": s.azure_openai_endpoint,
            "AZURE_OPENAI_DEPLOYMENT": s.azure_openai_deployment,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Azure OpenAI env vars missing: {', '.join(missing)}")

    base_url = _normalize_azure_endpoint(s.azure_openai_endpoint)
    # See note in _build_openrouter — tenacity owns retries; disable
    # the openai SDK's internal retry layer to avoid double-retry.
    client = AsyncOpenAI(
        api_key=s.azure_openai_api_key, base_url=base_url, max_retries=0
    )
    return LLM(
        client=client,
        # On Azure, `model` is the deployment name.
        model=s.azure_openai_deployment,
        provider="azure",
        # GPT-5 family only accepts default temperature → omit it.
        default_temperature=None,
        max_attempts=s.llm_max_attempts,
        retry_base_delay=s.llm_retry_base_delay,
        retry_max_delay=s.llm_retry_max_delay,
    )


def _normalize_azure_endpoint(raw: str) -> str:
    """Reduce any Azure endpoint string to the v1 OpenAI base URL.

    Accepts:
      * https://res.cognitiveservices.azure.com
      * https://res.cognitiveservices.azure.com/openai/v1/
      * https://res.cognitiveservices.azure.com/openai/responses?api-version=...
    Returns:
      * https://res.cognitiveservices.azure.com/openai/v1/
    """
    from urllib.parse import urlparse

    parsed = urlparse(raw.strip())
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError(f"AZURE_OPENAI_ENDPOINT is not a valid URL: {raw!r}")
    return f"{parsed.scheme}://{parsed.netloc}/openai/v1/"


@lru_cache(maxsize=1)
def get_llm() -> LLM:
    s = get_settings()
    builder = {"openrouter": _build_openrouter, "azure": _build_azure}[s.llm_provider]
    llm = builder()
    log.info("llm.configured", provider=llm.provider, model=llm.model)
    return llm
