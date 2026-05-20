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
from typing import Any

import requests

BASE: str = os.environ.get("BASE_URL", "http://localhost:13491").rstrip("/")
BROWSER_WS: str = os.environ.get("BROWSER_WS", "")


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




def login(user_name: str, password: str = "") -> str:
    """POST /login/password → bearer token. Aborts the test on failure."""
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
