"""E2E test: auth flow — admin login / logout / user login w/ DB+UI verify.

Bootstrap creates test_ad (admin) and test_usr_<YYYYMMDD> (user) if absent.

Steps:
  step_login_as_admin → DB: auth.users role=admin; UI: sidebar nav-logout visible
  step_logout         → DB: account still exists; UI: /login form visible
  step_login_as_user  → DB: auth.users role=user; UI: workspace in sidebar

Run:
  docker compose exec test-e2e python3 /scripts/e2e_test_auth.py
  docker compose exec test-e2e python3 /scripts/e2e_test_auth.py --snapshot
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from e2e_helper import E2E
from snapshot_decorator import set_snapshot_enabled, snapshot as step_snapshot
import bootstrap as _bootstrap

BASE_URL = os.environ.get("BASE_URL", "http://localhost:13491")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://dba_user:dba_pws@localhost:15432/db",
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _open_sidebar(ctx: E2E) -> None:
    """Click menu-toggle and wait for the 300ms CSS transition."""
    ctx.page.click('[data-testid="menu-toggle"]')
    ctx.page.wait_for_timeout(400)


# ── steps ─────────────────────────────────────────────────────────────────────

@step_snapshot
def step_login_as_admin(ctx: E2E, admin: dict) -> None:
    ctx.page.goto(f"{ctx.url}/login")
    ctx.page.wait_for_selector('[data-testid="login-userid"]', state="visible")

    ctx.page.fill('[data-testid="login-userid"]', admin["user_name"])
    ctx.page.click('[data-testid="login-start"]')

    # Home page redirects / → /{workspace_name}/; wait for nav-logout to exist
    # (indicates layout rendered with authenticated user).
    ctx.page.wait_for_selector(
        '[data-testid="nav-logout"]',
        state="attached",
        timeout=12000,
    )

    # DB: admin role confirmed
    row = ctx.assert_db(
        "SELECT role FROM auth.users WHERE user_id = %s",
        (admin["user_id"],),
        msg=f"admin {admin['user_id']} missing from auth.users",
    )
    assert row[0] == "admin", f"expected role=admin, got {row[0]!r}"

    # UI: sidebar opens, logout button visible
    _open_sidebar(ctx)
    ctx.assert_visible('[data-testid="nav-logout"]')


@step_snapshot
def step_logout(ctx: E2E, admin: dict) -> None:
    # Sidebar is open from the previous step — click logout directly
    ctx.page.click('[data-testid="nav-logout"]')

    ctx.page.wait_for_url(
        lambda url: url.endswith("/login"),
        timeout=6000,
    )

    # UI: login form visible
    ctx.assert_visible('[data-testid="login-userid"]')
    ctx.assert_visible('[data-testid="login-start"]')

    # UI: localStorage cleared
    stored = ctx.page.evaluate("localStorage.getItem('loginInfo')")
    assert stored is None, f"localStorage loginInfo not cleared: {stored}"

    # DB: account still intact (auth is client-side — no server session to purge)
    ctx.assert_db(
        "SELECT user_id FROM auth.users WHERE user_id = %s",
        (admin["user_id"],),
        msg="admin account disappeared after logout",
    )


@step_snapshot
def step_login_as_user(ctx: E2E, user: dict) -> None:
    # Already on /login from previous step
    ctx.page.wait_for_selector('[data-testid="login-userid"]', state="visible")

    ctx.page.fill('[data-testid="login-userid"]', user["user_name"])
    ctx.page.click('[data-testid="login-start"]')

    # Home page redirects / → /{workspace_name}/; wait for nav-logout to exist in
    # the DOM (indicates layout rendered with authenticated user) so we avoid
    # racing the intermediate navigation states.
    ctx.page.wait_for_selector(
        '[data-testid="nav-logout"]',
        state="attached",
        timeout=12000,
    )

    # DB: regular user with role=user
    row = ctx.assert_db(
        """
        SELECT au.role
          FROM auth.users au
          JOIN gdpr.user_info ui ON ui.user_id = au.user_id
         WHERE ui.user_name = %s
        """,
        (user["user_name"],),
        msg=f"user {user['user_name']!r} not found",
    )
    assert row[0] == "user", f"expected role=user, got {row[0]!r}"

    # UI: open sidebar; nav-logout visible means user is authenticated
    _open_sidebar(ctx)
    ctx.assert_visible('[data-testid="nav-logout"]')


# ── main ───────────────────────────────────────────────────────────────────────

def run(suffix: str, with_snapshot: bool) -> int:
    if with_snapshot:
        set_snapshot_enabled(True)

    print("[bootstrap] creating test fixtures …", file=sys.stderr)
    try:
        fixtures = _bootstrap.run(suffix=suffix, base=BASE_URL, dsn=DATABASE_URL)
    except Exception as exc:
        print(f"[bootstrap] FAILED: {exc}", file=sys.stderr)
        return 1

    admin = fixtures["admin"]
    user = fixtures["user"]
    print(
        f"[bootstrap] admin={admin['user_name']}  user={user['user_name']}",
        file=sys.stderr,
    )

    ctx = E2E(url=BASE_URL, dsn=DATABASE_URL)
    failed = False
    try:
        step_login_as_admin(ctx, admin)
        print("[ok] step_login_as_admin", file=sys.stderr)

        step_logout(ctx, admin)
        print("[ok] step_logout", file=sys.stderr)

        step_login_as_user(ctx, user)
        print("[ok] step_login_as_user", file=sys.stderr)

    except AssertionError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        failed = True
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        failed = True
    finally:
        ctx.close()

    if failed:
        return 1
    print("[PASS] all auth steps passed", file=sys.stderr)
    return 0


def main() -> int:
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    ap = argparse.ArgumentParser(description="E2E auth flow test")
    ap.add_argument("--suffix", default=today, help="user name suffix (default: YYYYMMDD)")
    ap.add_argument("--snapshot", action="store_true", help="save per-step screenshots")
    args = ap.parse_args()
    return run(suffix=args.suffix, with_snapshot=args.snapshot)


if __name__ == "__main__":
    sys.exit(main())
