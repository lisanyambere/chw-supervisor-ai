"""Unit tests for the async FHIR client (mocked with respx)."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.fhir.client import FhirClient, FhirError


BASE = "http://fake-openmrs/fhir/R4"


def _client() -> FhirClient:
    return FhirClient(
        base_url=BASE,
        username="admin",
        password="x",
        timeout=5.0,
    )


@pytest.mark.asyncio
@respx.mock
async def test_count_extracts_total() -> None:
    respx.get(f"{BASE}/Patient").mock(
        return_value=httpx.Response(
            200,
            json={"resourceType": "Bundle", "type": "searchset", "total": 581},
        )
    )
    async with _client() as fhir:
        total = await fhir.count("Patient")
    assert total == 581


@pytest.mark.asyncio
@respx.mock
async def test_search_paginates_until_no_next_link() -> None:
    page1 = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": {"id": "a"}}, {"resource": {"id": "b"}}],
        "link": [{"relation": "next", "url": f"{BASE}/Encounter?_getpages=PAGE2"}],
    }
    page2 = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": {"id": "c"}}],
        # No `next` link → stop.
    }

    route = respx.get(f"{BASE}/Encounter")
    route.mock(side_effect=[
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ])

    async with _client() as fhir:
        rows = await fhir.search("Encounter", {"subject": "uuid-1"})

    assert [r["id"] for r in rows] == ["a", "b", "c"]
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_search_respects_max_pages() -> None:
    bundle_with_next = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": {"id": "x"}}],
        "link": [{"relation": "next", "url": f"{BASE}/Encounter?_getpages=N"}],
    }
    route = respx.get(f"{BASE}/Encounter")
    route.mock(return_value=httpx.Response(200, json=bundle_with_next))

    async with _client() as fhir:
        rows = await fhir.search("Encounter", max_pages=2)

    assert len(rows) == 2
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_read_returns_resource() -> None:
    respx.get(f"{BASE}/Patient/uuid-1").mock(
        return_value=httpx.Response(
            200, json={"resourceType": "Patient", "id": "uuid-1"}
        )
    )
    async with _client() as fhir:
        res = await fhir.read("Patient", "uuid-1")
    assert res["id"] == "uuid-1"


@pytest.mark.asyncio
@respx.mock
async def test_4xx_raises_fhir_error_without_retry() -> None:
    route = respx.get(f"{BASE}/Patient/missing").mock(
        return_value=httpx.Response(404, text="not found")
    )
    async with _client() as fhir:
        with pytest.raises(FhirError):
            await fhir.read("Patient", "missing")
    assert route.call_count == 1  # 4xx must not retry


@pytest.mark.asyncio
@respx.mock
async def test_5xx_retries_then_succeeds() -> None:
    route = respx.get(f"{BASE}/Patient").mock(side_effect=[
        httpx.Response(503, text="busy"),
        httpx.Response(200, json={"resourceType": "Bundle", "total": 1}),
    ])
    async with _client() as fhir:
        total = await fhir.count("Patient")
    assert total == 1
    assert route.call_count == 2
