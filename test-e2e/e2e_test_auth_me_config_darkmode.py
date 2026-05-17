#!/usr/bin/env python3
"""task-52: e2e_test_auth_me_config_darkmode — PATCH /me/config persists dark mode.

Verifies:
 - Toggling dark mode in the UI sends PATCH /me/config {darkMode: true/false}
 - The <html> element gains/loses the 'dark' class
 - GET /me returns the persisted config after toggle
 - Preference survives a full page reload (server → localStorage → UI)

Usage:
    docker compose exec test-e2e python3 /scripts/e2e_test_auth_me_config_darkmode.py [--snapshot]
"""

import sys

from playwright.sync_api import sync_playwright

import e2e_base
from e2e_base import BASE, api, connect_browser, fatal, login, seed_login_info

SNAPSHOT = "--snapshot" in sys.argv
USER = "lattice"


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def run() -> None:
    # [0] Login
    print("[0] Login")
    token = login(USER)

    # [1] API: reset dark mode to OFF so test is idempotent
    print("[1] API: reset darkMode to false")
    r = api("PATCH", "/api/v1/login/me/config", token, json={"darkMode": False})
    if r.status_code != 200:
        fatal(f"PATCH /me/config reset failed: {r.status_code} {r.text[:200]}")
    assert r.json().get("darkMode") is False, "reset: expected darkMode=false"

    # [2] API: verify GET /me returns darkMode=false
    print("[2] API: verify GET /me config")
    r = api("GET", "/api/v1/login/me", token)
    if r.status_code != 200:
        fatal(f"GET /me failed: {r.status_code} {r.text[:200]}")
    assert r.json()["config"].get("darkMode") is False, "GET /me: expected darkMode=false"

    # [3] UI: open config page, verify toggle is OFF
    print("[3] UI: open /config, verify dark mode OFF")
    with sync_playwright() as pw:
        browser = connect_browser(pw)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        seed_login_info(ctx, token, USER, role="admin")
        page = ctx.new_page()

        page.goto(f"{BASE}/config", wait_until="networkidle")
        page.get_by_test_id("darkmode-toggle").wait_for(state="visible")
        snap(page, "01_config_dark_off")

        has_dark = page.evaluate("document.documentElement.classList.contains('dark')")
        assert has_dark is False, "expected <html> NOT to have 'dark' class initially"

        # [4] UI: click toggle → dark mode ON
        print("[4] UI: click darkmode toggle → ON")
        with page.expect_response("**/api/v1/login/me/config") as resp_info:
            page.get_by_test_id("darkmode-toggle").click()

        resp = resp_info.value
        assert resp.status == 200, f"PATCH response status: {resp.status}"
        resp_body = resp.json()
        assert resp_body.get("darkMode") is True, f"PATCH response: {resp_body}"

        snap(page, "02_config_dark_on")

        # [5] UI: verify <html> now has 'dark' class
        print("[5] UI: verify <html> has 'dark' class")
        page.wait_for_function("document.documentElement.classList.contains('dark')")

        # [6] API: verify persistence via GET /me
        print("[6] API: verify GET /me returns darkMode=true")
        r = api("GET", "/api/v1/login/me", token)
        assert r.json()["config"].get("darkMode") is True, "GET /me: expected darkMode=true after toggle"

        # [7] UI: reload page → dark mode should persist from server hydration
        print("[7] UI: reload → verify dark mode persists")
        page.reload(wait_until="networkidle")
        page.get_by_test_id("darkmode-toggle").wait_for(state="visible")
        page.wait_for_function("document.documentElement.classList.contains('dark')")
        snap(page, "03_config_dark_persisted")

        # [8] UI: toggle OFF again
        print("[8] UI: click darkmode toggle → OFF")
        with page.expect_response("**/api/v1/login/me/config") as resp_info:
            page.get_by_test_id("darkmode-toggle").click()

        resp = resp_info.value
        assert resp.status == 200
        assert resp.json().get("darkMode") is False

        page.wait_for_function("!document.documentElement.classList.contains('dark')")

        # [9] API: verify final state
        print("[9] API: verify GET /me returns darkMode=false")
        r = api("GET", "/api/v1/login/me", token)
        assert r.json()["config"].get("darkMode") is False, "GET /me: expected darkMode=false after toggle off"

        snap(page, "04_config_dark_off_final")
        browser.close()

    # [10] Teardown: ensure darkMode is reset to false (idempotent)
    api("PATCH", "/api/v1/login/me/config", token, json={"darkMode": False})
    print("PASS: e2e_test_auth_me_config_darkmode")


if __name__ == "__main__":
    run()
