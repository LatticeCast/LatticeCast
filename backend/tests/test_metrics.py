"""/metrics instrumentation: route templates only, no high-cardinality labels."""

from __future__ import annotations

import httpx
import pytest
from prometheus_client import REGISTRY, generate_latest

from main import app


def _sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.mark.asyncio
async def test_route_template_and_unmatched_are_labelled_without_raw_urls():
    transport = httpx.ASGITransport(app=app)
    labels = {"method": "GET", "route": "/api/v1/status", "status_class": "2xx"}
    before = _sample("lc_http_request_duration_seconds_count", **labels)
    unmatched_before = _sample(
        "lc_http_request_duration_seconds_count", method="GET", route="unmatched", status_class="4xx"
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/v1/status")).status_code == 200
        assert (await client.get("/api/v1/definitely-not-a-route-9f3a")).status_code == 404

    assert _sample("lc_http_request_duration_seconds_count", **labels) == before + 1
    assert (
        _sample("lc_http_request_duration_seconds_count", method="GET", route="unmatched", status_class="4xx")
        == unmatched_before + 1
    )
    assert b"definitely-not-a-route" not in generate_latest(REGISTRY)
    assert _sample("lc_http_requests_in_flight") == 0.0


def test_pool_gauges_are_zero_before_engines_exist():
    assert _sample("lc_db_pool_connections", engine="app", state="checked_out") >= 0.0
    assert _sample("lc_db_pool_size", engine="login") >= 0.0
