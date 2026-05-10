"""Async FHIR R4 client for OpenMRS."""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core import get_logger, get_settings

log = get_logger(__name__)


class FhirError(RuntimeError):
    """Raised on unrecoverable FHIR error."""


class FhirClient:
    """Thin async wrapper around the OpenMRS FHIR R4 endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        s = get_settings()
        self._base_url = (base_url or s.openmrs_fhir_url).rstrip("/")
        self._auth = (username or s.openmrs_api_user, password or s.openmrs_api_password)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            auth=self._auth,
            headers={"Accept": "application/fhir+json"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> FhirClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    # ─── low-level ──────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type(
                (httpx.TransportError, httpx.HTTPStatusError)
            ),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.get(path, params=params)
                if resp.status_code >= 500:
                    resp.raise_for_status()  # triggers retry
                if resp.status_code >= 400:
                    raise FhirError(
                        f"FHIR {resp.status_code} on {path}: {resp.text[:300]}"
                    )
                return resp.json()
        # Unreachable, but keeps type checker happy.
        raise FhirError("retry exhausted")

    # ─── high-level helpers ─────────────────────────────────────────────

    async def search(
        self,
        resource_type: str,
        params: dict[str, Any] | None = None,
        *,
        max_pages: int = 5,
    ) -> list[dict]:
        """Return concatenated `entry[].resource` lists across paginated bundles."""
        page = await self._get(f"/{resource_type}", params=params)
        out: list[dict] = [e["resource"] for e in (page.get("entry") or [])]

        pages_fetched = 1
        while pages_fetched < max_pages:
            next_url = _next_link(page)
            if not next_url:
                break
            # OpenMRS returns absolute URLs; strip prefix if it matches base.
            path = _to_relative(next_url, self._base_url)
            page = await self._get(path)
            out.extend(e["resource"] for e in (page.get("entry") or []))
            pages_fetched += 1

        return out

    async def count(self, resource_type: str, params: dict[str, Any] | None = None) -> int:
        merged = {"_summary": "count", **(params or {})}
        page = await self._get(f"/{resource_type}", params=merged)
        return int(page.get("total", 0))

    async def read(self, resource_type: str, resource_id: str) -> dict:
        return await self._get(f"/{resource_type}/{resource_id}")


def _next_link(bundle: dict) -> str | None:
    for link in bundle.get("link") or []:
        if link.get("relation") == "next":
            return link.get("url")
    return None


def _to_relative(url: str, base: str) -> str:
    if url.startswith(base):
        return url[len(base):]
    # Fallback: just use the absolute URL; httpx will accept it.
    return url
