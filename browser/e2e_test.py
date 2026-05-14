"""End-to-end FE smoke test — exercises the v40 refactor surfaces.

Runs each step independently. A failure in one step doesn't abort the
others; instead the step is marked as failed and the run continues so
we get full coverage in one pass. Exit code is non-zero if ANY step
errors so this can be wired into CI later.

Steps tested (each is independent):
  1. workspace landing page renders
  2. POST /workspaces — creates a new workspace via FE
  3. POST /tables — creates a blank table via FE
  4. POST /tables/template/pm — PM template via FE
  5. PATCH /tables/{tid}/columns/{cid} — update column color via FE

Errors and 4xx/5xx HTTP responses are tagged with the step they
happened in. Screenshots go to /output/ for visual review.
"""

import json
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

LATTICE_UID = "1ad4977f-f2aa-4a87-8f15-568d7c7aed59"
WORKSPACE_ID = "de492911-9d4e-4568-9189-497767d6f8a5"
BASE = "http://localhost:13491"

LOGIN_INFO = json.dumps({
    "provider": "none",
    "accessToken": LATTICE_UID,
    "userInfo": {"sub": LATTICE_UID, "email": "lattice@example.com", "name": "lattice"},
    "role": "admin",
})


class Report:
    def __init__(self):
        self.events: list[str] = []
        self.failed_steps: set[str] = set()
        self.current_step = "init"

    def step(self, name: str) -> None:
        self.current_step = name
        self.events.append(f"\n— step: {name}")

    def err(self, msg: str) -> None:
        self.events.append(f"  [{self.current_step}] FAIL: {msg}")
        self.failed_steps.add(self.current_step)

    def info(self, msg: str) -> None:
        self.events.append(f"  [{self.current_step}] {msg}")


def install_hooks(page, r: Report) -> None:
    page.on("console", lambda m: r.err(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: r.err(f"pageerror: {e}"))

    def on_response(resp):
        if resp.status >= 400:
            r.err(f"HTTP {resp.status} {resp.request.method} {resp.url}")
    page.on("response", on_response)


def run() -> int:
    r = Report()
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 900})
        install_hooks(page, r)

        # ── 1: landing ────────────────────────────────────────────────
        r.step("1_landing")
        try:
            page.goto(BASE, wait_until="domcontentloaded")
            page.evaluate(f"localStorage.setItem('loginInfo', {json.dumps(LOGIN_INFO)})")
            page.goto(f"{BASE}/{WORKSPACE_ID}", wait_until="networkidle")
            page.wait_for_timeout(1200)
            page.screenshot(path="/output/smoke_1_landing.png", full_page=True)
            if "lattice" not in page.content():
                r.err("breadcrumb missing 'lattice'")
        except Exception as exc:
            r.err(f"exception: {exc}")

        # ── 2: create workspace ──────────────────────────────────────
        r.step("2_create_workspace")
        try:
            ts = int(time.time())
            ws_name = f"smoke_ws_{ts}"
            resp = page.evaluate(
                """async ({base, token, name}) => {
                    const r = await fetch(base + '/api/v1/workspaces', {
                        method: 'POST',
                        headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                        body: JSON.stringify({workspace_name: name})
                    });
                    return {status: r.status, body: await r.text()};
                }""",
                {"base": BASE, "token": LATTICE_UID, "name": ws_name}
            )
            if resp["status"] != 201:
                r.err(f"status={resp['status']} body={resp['body'][:200]}")
            else:
                r.info(f"created '{ws_name}'")
        except Exception as exc:
            r.err(f"exception: {exc}")

        # ── 3: create blank table ────────────────────────────────────
        r.step("3_create_blank_table")
        try:
            ts = int(time.time())
            tid = f"smoke_blank_{ts}"
            resp = page.evaluate(
                """async ({base, token, tid, ws}) => {
                    const r = await fetch(base + '/api/v1/tables', {
                        method: 'POST',
                        headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                        body: JSON.stringify({table_id: tid, workspace_id: ws})
                    });
                    return {status: r.status, body: await r.text()};
                }""",
                {"base": BASE, "token": LATTICE_UID, "tid": tid, "ws": WORKSPACE_ID}
            )
            if resp["status"] != 201:
                r.err(f"status={resp['status']} body={resp['body'][:200]}")
            else:
                r.info(f"created '{tid}'")
        except Exception as exc:
            r.err(f"exception: {exc}")

        # ── 4: PM template ────────────────────────────────────────────
        r.step("4_create_pm_template")
        try:
            ts = int(time.time())
            tid = f"smoke_pm_{ts}"
            resp = page.evaluate(
                """async ({base, token, tid, ws}) => {
                    const r = await fetch(base + '/api/v1/tables/template/pm', {
                        method: 'POST',
                        headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                        body: JSON.stringify({table_id: tid, workspace_id: ws})
                    });
                    return {status: r.status, body: await r.text()};
                }""",
                {"base": BASE, "token": LATTICE_UID, "tid": tid, "ws": WORKSPACE_ID}
            )
            if resp["status"] != 201:
                r.err(f"status={resp['status']} body={resp['body'][:300]}")
            else:
                r.info(f"created '{tid}' with PM template")
                # Capture the response to find Status column for next step
                r.last_pm_response = json.loads(resp["body"])
        except Exception as exc:
            r.err(f"exception: {exc}")

        # ── 5: update column color ────────────────────────────────────
        r.step("5_update_column_color")
        try:
            # Use the existing demo_pm table — find Status column
            cols_resp = page.evaluate(
                """async ({base, token}) => {
                    const r = await fetch(base + '/api/v1/tables/demo_pm', {
                        headers: {'Authorization': 'Bearer ' + token}
                    });
                    return {status: r.status, body: await r.text()};
                }""",
                {"base": BASE, "token": LATTICE_UID}
            )
            if cols_resp["status"] != 200:
                r.err(f"GET demo_pm: status={cols_resp['status']}")
            else:
                table = json.loads(cols_resp["body"])
                status_col = next((c for c in table["columns"] if c["name"] == "Status"), None)
                if not status_col:
                    r.err("Status column not found in demo_pm")
                else:
                    cid = status_col["column_id"]
                    new_options = {
                        "choices": [
                            {"value": "todo", "color": "#ff00ff"},
                            {"value": "done", "color": "#00ff00"},
                        ]
                    }
                    upd_resp = page.evaluate(
                        """async ({base, token, tid, cid, opts}) => {
                            const r = await fetch(base + '/api/v1/tables/' + tid + '/columns/' + cid, {
                                method: 'PATCH',
                                headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                                body: JSON.stringify({options: opts})
                            });
                            return {status: r.status, body: await r.text()};
                        }""",
                        {"base": BASE, "token": LATTICE_UID, "tid": "demo_pm", "cid": cid, "opts": new_options}
                    )
                    if upd_resp["status"] not in (200, 201):
                        r.err(f"PATCH column: status={upd_resp['status']} body={upd_resp['body'][:300]}")
                    else:
                        r.info(f"updated Status column ({cid}) colors")
        except Exception as exc:
            r.err(f"exception: {exc}")

        # ── 6b: update view config (group_by) — must echo views[] back
        r.step("6b_update_view_config")
        try:
            resp = page.evaluate(
                """async ({base, token}) => {
                    // Find Sprint Board view_id from demo_pm
                    const tr = await fetch(base + '/api/v1/tables/demo_pm', {
                        headers: {'Authorization': 'Bearer ' + token}
                    });
                    const table = await tr.json();
                    const board = (table.views || []).find(v => v.name === 'Sprint Board');
                    if (!board) return {status: 0, body: 'no Sprint Board view'};
                    const r = await fetch(base + '/api/v1/tables/demo_pm/views/' + board.view_id, {
                        method: 'PUT',
                        headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                        body: JSON.stringify({config: {group_by: 'placeholder_col'}})
                    });
                    const body = await r.json();
                    return {status: r.status, viewsCount: (body.views || []).length, body: JSON.stringify(body).slice(0, 200)};
                }""",
                {"base": BASE, "token": LATTICE_UID}
            )
            if resp["status"] != 200:
                r.err(f"status={resp['status']} body={resp.get('body')}")
            elif resp["viewsCount"] == 0:
                r.err(f"response missing views[] array; body={resp.get('body')}")
            else:
                r.info(f"updated view config; response views[]={resp['viewsCount']}")
        except Exception as exc:
            r.err(f"exception: {exc}")

        # ── 6: PATCH /me/config — per-user UI config ─────────────────
        r.step("6_patch_me_config")
        try:
            resp = page.evaluate(
                """async ({base, token}) => {
                    const r = await fetch(base + '/api/v1/login/me/config', {
                        method: 'PATCH',
                        headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                        body: JSON.stringify({darkMode: true})
                    });
                    return {status: r.status, body: await r.text()};
                }""",
                {"base": BASE, "token": LATTICE_UID}
            )
            if resp["status"] not in (200, 201):
                r.err(f"PATCH /me/config: status={resp['status']} body={resp['body'][:200]}")
            else:
                r.info("set darkMode=true on UserInfo.config")
        except Exception as exc:
            r.err(f"exception: {exc}")

        # ── Final screenshot ────────────────────────────────────
        page.screenshot(path="/output/smoke_final.png", full_page=True)
        b.close()

    print("\n".join(r.events))
    print("\n=== SUMMARY ===")
    if r.failed_steps:
        print(f"FAILED: {sorted(r.failed_steps)}")
        return 1
    print("ALL STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run())
