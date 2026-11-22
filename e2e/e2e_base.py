"""Shared bootstrap for e2e_test_*.py — one source of truth.

Test files import from here instead of redefining env / reroute / auth
boilerplate. Keeps the per-test scripts focused on one topic.

Exports:
    BASE        — backend base URL (BASE_URL env, default http://localhost:13491)
    BROWSER_WS  — playwright remote ws URL (BROWSER_WS env)
    login(user_name, password="") -> token
    api(method, path, token, **kw) -> requests.Response
    make_login_info(token, user_name, role="admin") -> JSON str
    seed_login_info(page, token, user_name, role="admin") -> None
                — seeds localStorage('loginInfo') so the SPA boots
                  authenticated. Must be called BEFORE the first goto.
    fatal(msg) -> None  (sys.exit(1) with FAIL prefix)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any

import requests

BASE: str = os.environ.get("BASE_URL", "http://localhost:13491").rstrip("/")
BROWSER_WS: str = os.environ.get("BROWSER_WS", "")

# --- Pacing -----------------------------------------------------------------
# The deployed target sits behind a CloudFront WAF that blocks one IP at
# ~3000 requests / 5 min (login: 100 / 5 min); the local nginx emulates it.
# Every request to BASE, API or browser, goes through one shared throttle.
# E2E_MAX_RPS overrides (0 disables).
MAX_RPS: float = float(os.environ.get("E2E_MAX_RPS", "4"))
BURST: float = float(os.environ.get("E2E_BURST", "10"))
_throttle_lock = threading.Lock()
_tokens = BURST
_last_refill = time.monotonic()


def throttle() -> None:
    """Token bucket shared by API calls and browser requests: MAX_RPS on average,
    with a small burst so deliberately concurrent requests are not forced into a queue."""
    global _tokens, _last_refill
    if MAX_RPS <= 0:
        return
    with _throttle_lock:
        now = time.monotonic()
        _tokens = min(BURST, _tokens + (now - _last_refill) * MAX_RPS)
        _last_refill = now
        wait = 0.0 if _tokens >= 1 else (1 - _tokens) / MAX_RPS
        _tokens -= 1
    if wait > 0:
        time.sleep(wait)


def is_cloudfront_block(status: int, server: str, body: str) -> bool:
    """A real WAF block, not a backend 403 relayed through CloudFront.

    CloudFront adds `x-cache: Error from cloudfront` to every non-2xx it relays, so that
    header proves nothing. A WAF block is answered by CloudFront itself: `Server: CloudFront`
    and an HTML "The request could not be satisfied" page; a backend 403 is JSON from uvicorn.
    """
    if status != 403:
        return False
    if server.strip().lower() == "cloudfront":
        return True
    text = body.lstrip().lower()
    return text.startswith("<!doctype html") and "the request could not be satisfied" in text


def waf_block_abort(where: str, status: int, server: str, body: str) -> None:
    """Fail the whole run at once with a clear message instead of cascading 403s."""
    if is_cloudfront_block(status, server, body):
        import pytest

        pytest.exit(
            f"CloudFront/WAF 403 on {where}: this IP is rate-limited (3000 req / 100 logins per 5 min). "
            f"Lower E2E_MAX_RPS (now {MAX_RPS}), wait 5 minutes, and rerun. Not retrying.",
            returncode=3,
        )


if MAX_RPS > 0:
    _orig_session_request = requests.Session.request

    def _paced_request(self, method, url, *args, **kw):
        if isinstance(url, str) and url.startswith(BASE):
            throttle()
        resp = _orig_session_request(self, method, url, *args, **kw)
        if isinstance(url, str) and url.startswith(BASE):
            waf_block_abort(f"{method} {url}", resp.status_code, resp.headers.get("server", ""), resp.text[:500])
        return resp

    requests.Session.request = _paced_request  # also covers requests.get/post/put/request


def pace_browser(browser):
    """Throttle every browser request to BASE (all pages and contexts) and abort on a CloudFront 403."""
    # The local vite dev server serves hundreds of modules per page; pace the browser
    # only against a deployed (bundled) target.
    if MAX_RPS <= 0 or not BASE.startswith("https://"):
        return browser

    def _route(route):
        if route.request.url.startswith(BASE):
            throttle()
        route.continue_()

    def _response(resp):
        if resp.url.startswith(BASE) and resp.status == 403:
            waf_block_abort(resp.url, 403, resp.headers.get("server", ""), "")

    def _arm(ctx):
        ctx.route("**/*", _route)
        ctx.on("response", _response)
        return ctx

    new_context, new_page = browser.new_context, browser.new_page

    def paced_new_context(*a, **kw):
        return _arm(new_context(*a, **kw))

    def paced_new_page(*a, **kw):
        page = new_page(*a, **kw)
        _arm(page.context)
        return page

    browser.new_context, browser.new_page = paced_new_context, paced_new_page
    return browser


def connect_browser(pw):
    """Connect to the playwright run-server in the `browser` container.

    e2e has no local Chromium — fall back is not an option. We fail
    loud if BROWSER_WS isn't set rather than pretend the test can
    proceed.
    """
    if not BROWSER_WS:
        fatal("BROWSER_WS env var not set — must point at ws://browser:4444")
    return pw.chromium.connect(BROWSER_WS)


def fatal(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)




_login_cache: dict[tuple[str, str], str] = {}


def login(user_name: str, password: str = "") -> str:
    """POST /login/password → bearer token (cached per run: the login limit is 100 / 5 min).

    Aborts the test on failure."""
    if (user_name, password) in _login_cache:
        return _login_cache[(user_name, password)]
    token = _login(user_name, password)
    _login_cache[(user_name, password)] = token
    return token


def _login(user_name: str, password: str) -> str:
    r = requests.post(
        f"{BASE}/api/v1/login/password",
        json={"user_name": user_name, "password": password},
        timeout=10,
    )
    if r.status_code != 200:
        fatal(f"login {user_name!r}: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def api(method: str, path: str, token: str, **kw) -> requests.Response:
    """Authenticated request helper. `path` is the FastAPI path (with leading /)."""
    return requests.request(
        method,
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=kw.pop("timeout", 15),
        **kw,
    )


def create_blank_table(token: str, table_name: str, workspace: str) -> str:
    """Create a blank table and return its identity, as text for URL building.

    The API takes `table_name` and answers with the database-assigned `table_id`,
    which is what every table-scoped path expects.
    """
    r = api(
        "POST",
        "/api/v1/tables",
        token,
        json={"table_name": table_name, "workspace_id": workspace},
    )
    assert r.status_code == 201, f"create table {table_name!r}: {r.status_code} {r.text[:200]}"
    return str(r.json()["table_id"])


def create_template_table(
    token: str, kind: str, table_name: str, workspace_name: str
) -> dict:
    """Create a template table and return the created table body (numeric table_id)."""
    r = api(
        "POST",
        f"/api/v1/tables/template/{kind}",
        token,
        json={"table_name": table_name, "workspace_name": workspace_name},
    )
    assert r.status_code == 201, f"create {kind} table {table_name!r}: {r.status_code} {r.text[:200]}"
    return r.json()


def make_login_info(token: str, user_name: str, role: str = "admin") -> str:
    """Build the JSON the FE stores at localStorage('loginInfo')."""
    return json.dumps({
        "provider": "none",
        "accessToken": token,
        "userInfo": {
            "sub": token,
            "email": f"{user_name}@e2e.local",
            "name": user_name,
        },
        "role": role,
    })


def seed_login_info(page, token: str, user_name: str, role: str = "admin") -> None:
    """Inject loginInfo into localStorage BEFORE the first goto.

    Use `page.add_init_script` so the value is set on every navigation
    in this page's lifetime — the SPA reads localStorage during boot.
    """
    info = make_login_info(token, user_name, role)
    page.add_init_script(f"localStorage.setItem('loginInfo', {json.dumps(info)});")
