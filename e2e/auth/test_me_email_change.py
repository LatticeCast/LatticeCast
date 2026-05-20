"""task-82: auth/test_me_email_change — email rotate via login_session.

Verifies:
 - Changing email in /settings UI sends PUT /login/me/email
 - Success response updates the displayed email
 - GET /me returns the new email (DB persistence via login_session)
 - Email persists after full page reload
 - Conflict (409) when attempting to use another user's email

Usage:
    docker compose exec -T e2e pytest auth/test_me_email_change.py -v
    E2E_SNAPSHOT=1 docker compose exec -T e2e pytest auth/test_me_email_change.py -v
"""

import os
import time

from e2e_base import BASE, api

SNAPSHOT = os.environ.get("E2E_SNAPSHOT", "") in ("1", "true")
USER = "lattice"
SUFFIX = int(time.time()) % 100000
NEW_EMAIL = f"lattice-rotated-{SUFFIX}@e2e.local"
CONFLICT_EMAIL = f"e2e-conflict-{SUFFIX}@e2e.local"


def snap(page, name: str) -> None:
    if not SNAPSHOT:
        return
    try:
        page.screenshot(path=f"/output/{name}.png", full_page=True)
    except Exception:
        pass


def test_me_email_change(authed_page, admin_token):
    page = authed_page
    token = admin_token

    # [0] Discover current email
    print("[0] Discover current email")
    r = api("GET", "/api/v1/login/me", token)
    assert r.status_code == 200, f"GET /me failed: {r.status_code} {r.text[:200]}"
    original_email = r.json()["email"]
    print(f"    original email: {original_email}")

    # [1] Reset email to original (idempotent start)
    print("[1] API: reset email to original")
    r = api("PUT", "/api/v1/login/me/email", token, json={"email": original_email})
    assert r.status_code == 200, f"PUT /me/email reset failed: {r.status_code} {r.text[:200]}"

    # [2] Create a second user for the conflict test
    print(f"[2] Setup: create conflict user '{CONFLICT_EMAIL}'")
    api("DELETE", f"/api/v1/admin/users/{CONFLICT_EMAIL}", token)
    r = api("POST", "/api/v1/admin/users", token, json={"email": CONFLICT_EMAIL, "role": "user"})
    assert r.status_code == 201, f"create conflict user: {r.status_code} {r.text[:200]}"

    try:
        # [3] UI: open settings page, verify current email shown
        print("[3] UI: open /settings, verify email input")
        page.goto(f"{BASE}/settings", wait_until="networkidle")
        page.get_by_test_id("settings-email-input").wait_for(state="visible")
        snap(page, "01_settings_initial")

        current_value = page.get_by_test_id("settings-email-input").input_value()
        assert current_value == original_email, (
            f"expected input to show '{original_email}', got '{current_value}'"
        )

        # [4] UI: change email → verify PUT response
        print(f"[4] UI: change email to '{NEW_EMAIL}'")
        email_input = page.get_by_test_id("settings-email-input")
        email_input.click()
        email_input.fill(NEW_EMAIL)

        save_btn = page.get_by_test_id("settings-save-btn")
        save_btn.wait_for(state="visible")

        with page.expect_response("**/api/v1/login/me/email") as resp_info:
            save_btn.click()

        resp = resp_info.value
        assert resp.status == 200, f"PUT response status: {resp.status}"
        resp_body = resp.json()
        assert resp_body["email"] == NEW_EMAIL, f"PUT response email: {resp_body.get('email')}"
        snap(page, "02_email_changed")

        # [5] UI: verify success message
        print("[5] UI: verify success message")
        success_el = page.get_by_test_id("settings-success")
        success_el.wait_for(state="visible", timeout=5000)
        success_text = success_el.text_content() or ""
        assert "updated" in success_text.lower(), f"expected 'updated' in '{success_text}'"

        # [6] API: verify GET /me returns new email
        print("[6] API: verify GET /me returns new email")
        r = api("GET", "/api/v1/login/me", token)
        assert r.status_code == 200, f"GET /me: {r.status_code}"
        assert r.json()["email"] == NEW_EMAIL, (
            f"GET /me email: expected '{NEW_EMAIL}', got '{r.json()['email']}'"
        )

        # [7] UI: reload → email persists
        print("[7] UI: reload → verify email persists")
        page.reload(wait_until="networkidle")
        page.get_by_test_id("settings-email-input").wait_for(state="visible")
        reloaded_value = page.get_by_test_id("settings-email-input").input_value()
        assert reloaded_value == NEW_EMAIL, (
            f"after reload: expected '{NEW_EMAIL}', got '{reloaded_value}'"
        )
        snap(page, "03_email_persisted")

        # [8] UI: attempt conflict email → 409 error
        print(f"[8] UI: attempt conflict email '{CONFLICT_EMAIL}'")
        email_input = page.get_by_test_id("settings-email-input")
        email_input.click()
        email_input.fill(CONFLICT_EMAIL)

        with page.expect_response("**/api/v1/login/me/email") as resp_info:
            page.get_by_test_id("settings-save-btn").click()

        resp = resp_info.value
        assert resp.status == 409, f"expected 409, got {resp.status}"

        # [9] UI: verify error message
        print("[9] UI: verify conflict error message")
        error_el = page.get_by_test_id("settings-error")
        error_el.wait_for(state="visible", timeout=5000)
        error_text = error_el.text_content() or ""
        assert "already registered" in error_text.lower(), (
            f"expected 'already registered' in '{error_text}'"
        )
        snap(page, "04_conflict_error")

        # [10] API: verify email unchanged after conflict
        print("[10] API: verify email unchanged after conflict")
        r = api("GET", "/api/v1/login/me", token)
        assert r.json()["email"] == NEW_EMAIL, (
            f"email should still be '{NEW_EMAIL}' after 409, got '{r.json()['email']}'"
        )

    finally:
        # [11] Teardown: restore original email + delete conflict user
        print("[11] Teardown: restore email + delete conflict user")
        api("PUT", "/api/v1/login/me/email", token, json={"email": original_email})
        api("DELETE", f"/api/v1/admin/users/{CONFLICT_EMAIL}", token)

    print("PASS: auth/test_me_email_change")
