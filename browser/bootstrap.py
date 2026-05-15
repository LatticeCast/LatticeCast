"""Bootstrap e2e test fixtures: PG admin INSERT + BE create user/workspace.

Usage:
    python bootstrap.py [--suffix YYYYMMDD] [--base-url URL] [--db-url DSN]

Outputs JSON with admin and user credentials for test scripts to consume.

Steps:
  1. PG INSERT admin user (idempotent — ON CONFLICT DO NOTHING)
  2. BE POST /login/password → admin token
  3. BE POST /admin/users   → create test regular user (auto-creates workspace)
  4. BE POST /login/password → user token
  5. BE GET /workspaces     → resolve workspace_id

Exit 0 on success, 1 on any failure.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import psycopg2
import requests

ADMIN_USER_ID = "00000000-0000-0000-0000-000000000ad1"
ADMIN_USER_NAME = "test_ad"
ADMIN_EMAIL = "test_ad@e2e.local"

DEFAULT_BASE_URL = os.environ.get("BASE_URL", "http://localhost:13491")
DEFAULT_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://dba_user:dba_pws@localhost:15432/db",
)


def _pg_bootstrap_admin(dsn: str) -> None:
    """Insert admin user into auth.users + gdpr.user_info (idempotent)."""
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth.users (user_id, role)
                VALUES (%s, 'admin')
                ON CONFLICT (user_id) DO NOTHING
                """,
                (ADMIN_USER_ID,),
            )
            cur.execute(
                """
                INSERT INTO gdpr.user_info (user_id, email, user_name, config)
                VALUES (%s, %s, %s, '{}'::JSONB)
                ON CONFLICT (user_id) DO NOTHING
                """,
                (ADMIN_USER_ID, ADMIN_EMAIL, ADMIN_USER_NAME),
            )
    finally:
        conn.close()


def _be_login(base: str, user_name: str) -> str:
    """POST /login/password → access_token (AUTH_REQUIRED=false mode)."""
    r = requests.post(
        f"{base}/api/v1/login/password",
        json={"user_name": user_name, "password": ""},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"login {user_name!r} failed {r.status_code}: {r.text[:200]}")
    return r.json()["access_token"]


def _be_create_user(base: str, admin_token: str, email: str, user_name: str) -> dict:
    """POST /admin/users → UserResponse (also bootstraps workspace via bootstrap_user)."""
    r = requests.post(
        f"{base}/api/v1/admin/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": email, "role": "user", "user_name": user_name},
        timeout=10,
    )
    if r.status_code == 409:
        return {"exists": True, "email": email}
    if r.status_code != 201:
        raise RuntimeError(f"create user {email!r} failed {r.status_code}: {r.text[:200]}")
    return r.json()


def _be_get_workspace(base: str, token: str, workspace_name: str) -> str | None:
    """GET /workspaces → find workspace_id whose name matches workspace_name."""
    r = requests.get(
        f"{base}/api/v1/workspaces",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"list workspaces failed {r.status_code}: {r.text[:200]}")
    for ws in r.json():
        if ws.get("workspace_name") == workspace_name:
            return ws["workspace_id"]
    return None


def run(suffix: str, base: str, dsn: str) -> dict:
    user_name = f"test_usr_{suffix}"
    email = f"{user_name}@e2e.local"

    # Step 1: PG — admin user
    print(f"[1] PG INSERT admin ({ADMIN_EMAIL})", file=sys.stderr)
    _pg_bootstrap_admin(dsn)

    # Step 2: BE — admin login
    print("[2] BE login admin", file=sys.stderr)
    admin_token = _be_login(base, ADMIN_USER_NAME)

    # Step 3: BE — create regular user (auto-creates default workspace)
    print(f"[3] BE create user {email!r}", file=sys.stderr)
    user_resp = _be_create_user(base, admin_token, email, user_name)
    existed = user_resp.get("exists", False)
    if existed:
        print(f"    user already exists — skipping create", file=sys.stderr)

    # Step 4: BE — regular user login
    print(f"[4] BE login {user_name!r}", file=sys.stderr)
    user_token = _be_login(base, user_name)

    # Step 5: BE — resolve workspace_id (workspace_name = email per bootstrap_user)
    print("[5] BE resolve workspace", file=sys.stderr)
    workspace_id = _be_get_workspace(base, user_token, email)
    if workspace_id is None:
        raise RuntimeError(f"default workspace for {email!r} not found")

    result = {
        "admin": {
            "user_id": ADMIN_USER_ID,
            "user_name": ADMIN_USER_NAME,
            "email": ADMIN_EMAIL,
            "token": admin_token,
        },
        "user": {
            "user_name": user_name,
            "email": email,
            "token": user_token,
            "workspace_id": workspace_id,
        },
    }
    print("[ok] bootstrap complete", file=sys.stderr)
    return result


def main() -> int:
    today = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
    parser = argparse.ArgumentParser(description="Bootstrap e2e test fixtures")
    parser.add_argument("--suffix", default=today, help="User name suffix (default: YYYYMMDD)")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--db-url", default=DEFAULT_DB_URL)
    args = parser.parse_args()

    try:
        result = run(suffix=args.suffix, base=args.base_url, dsn=args.db_url)
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
