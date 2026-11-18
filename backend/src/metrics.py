"""Prometheus instrumentation.

One uvicorn worker per container, so the plain in-process registry is enough:
scale by running more containers and let Prometheus scrape each one. Metrics are
served on their own port (METRICS_PORT, default 9100), which is never published
or routed through nginx/ALB.

Labels stay low-cardinality on purpose: the route *template*, the method, the
status class, and the pool name. Never workspace_id, user_id, or a raw URL.
"""

from __future__ import annotations

import asyncio
import os
import time

from prometheus_client import Gauge, Histogram, start_http_server

import core.db as core_db

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)

HTTP_REQUEST_SECONDS = Histogram(
    "lc_http_request_duration_seconds",
    "API request duration by route template.",
    ("method", "route", "status_class"),
    buckets=LATENCY_BUCKETS,
)
HTTP_IN_FLIGHT = Gauge("lc_http_requests_in_flight", "API requests currently being handled.")
DB_POOL_CONNECTIONS = Gauge(
    "lc_db_pool_connections",
    "SQLAlchemy pool connections by engine and state (checked_out, checked_in, overflow).",
    ("engine", "state"),
)
DB_POOL_SIZE = Gauge("lc_db_pool_size", "Configured SQLAlchemy pool_size per engine.", ("engine",))


EVENT_LOOP_LAG_SECONDS = Histogram(
    "lc_event_loop_lag_seconds",
    "How late the event loop wakes a timer; blocking calls on the loop show up here.",
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
LOOP_LAG_INTERVAL = 0.1


async def event_loop_lag_loop() -> None:
    """Sleep a fixed interval and record how much later than that it resumed."""
    loop = asyncio.get_running_loop()
    while True:
        expected = loop.time() + LOOP_LAG_INTERVAL
        await asyncio.sleep(LOOP_LAG_INTERVAL)
        EVENT_LOOP_LAG_SECONDS.observe(max(loop.time() - expected, 0.0))


class MetricsMiddleware:
    """Pure ASGI middleware: cheaper than BaseHTTPMiddleware and keeps streaming intact."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status = 500
        started = time.perf_counter()

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        HTTP_IN_FLIGHT.inc()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            HTTP_IN_FLIGHT.dec()
            # Starlette stores the matched route on the shared scope while routing.
            route = getattr(scope.get("route"), "path", None) or "unmatched"
            HTTP_REQUEST_SECONDS.labels(scope["method"], route, f"{status // 100}xx").observe(
                time.perf_counter() - started
            )


def _pool_reader(engine_attr: str, read):
    """Read a pool value at scrape time; 0 until the engine exists."""

    def value() -> float:
        engine = getattr(core_db, engine_attr)
        return float(read(engine.sync_engine.pool)) if engine is not None else 0.0

    return value


for _name, _attr in (("app", "app_engine"), ("login", "login_engine")):
    DB_POOL_SIZE.labels(_name).set_function(_pool_reader(_attr, lambda pool: pool.size()))
    DB_POOL_CONNECTIONS.labels(_name, "checked_out").set_function(_pool_reader(_attr, lambda pool: pool.checkedout()))
    DB_POOL_CONNECTIONS.labels(_name, "checked_in").set_function(_pool_reader(_attr, lambda pool: pool.checkedin()))
    DB_POOL_CONNECTIONS.labels(_name, "overflow").set_function(
        _pool_reader(_attr, lambda pool: max(pool.overflow(), 0))
    )


def start_metrics_server():
    """Serve /metrics on METRICS_PORT. Returns the server, or None if it cannot bind."""
    port = int(os.environ.get("METRICS_PORT", "9100"))
    try:
        server, _thread = start_http_server(port)
    except OSError as exc:  # metrics must never take the API down
        print(f"⚠ metrics server not started on :{port}: {exc}")
        return None
    return server
