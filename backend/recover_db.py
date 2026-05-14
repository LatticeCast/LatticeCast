#!/usr/bin/env python3
"""
recover_db.py — copy data from `db_backup` (old V42 schema) into fresh `db`
(new squashed V1-V17 schema).

Run inside the backend container (has psycopg available):

    docker compose exec backend python3 /jetbase/recover_db.py [--dry-run]

Or with explicit DSNs:

    docker compose exec backend python3 /jetbase/recover_db.py \
        --src postgresql://dba_user:dba_pws@db:5432/db_backup \
        --dst postgresql://dba_user:dba_pws@db:5432/db

The script connects as dba_user (superuser-ish, bypasses RLS) so policies don't
filter anything out.

Mapping (per the v0.40 squash):
    auth.users                              → auth.users           (1-to-1)
    auth.gdpr ⨝ public.user_info            → gdpr.user_info       (merge)
    public.workspaces                       → public.workspaces    (1-to-1)
    public.workspace_members                → public.workspace_members (1-to-1)
    public.tables                           → public.tables        (1-to-1, trigger creates empty schema row, we overwrite)
    public.table_views WHERE name='__schema__'  → table_schemas.config.columns
    public.table_views WHERE name='__order__'   → table_schemas.config.view_order (translated to view_ids)
    public.table_views user views           → public.table_views   (name+type folded INTO config, new bigint view_id assigned by trigger)
    public.rows (row_number)                → public.rows (row_id) (explicit value preserved)

Not covered (acceptable for first pass):
    - Per-column row_data GIN/B-tree indexes — recreate later via API or
      a follow-up index-rebuild script. Correctness not affected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

try:
    import psycopg  # psycopg3

    PSYCOPG = "psycopg"
except ImportError:  # pragma: no cover
    import psycopg2 as psycopg  # type: ignore

    PSYCOPG = "psycopg2"


def parse_args():
    p = argparse.ArgumentParser()
    base = os.environ.get("DATABASE_URL", "postgresql://dba_user:dba_pws@db:5432/db")
    p.add_argument("--src", default=base.rsplit("/", 1)[0] + "/db_backup")
    p.add_argument("--dst", default=base.rsplit("/", 1)[0] + "/db")
    p.add_argument("--dry-run", action="store_true", help="print counts only, no writes")
    return p.parse_args()


def connect(dsn: str):
    if PSYCOPG == "psycopg":
        return psycopg.connect(dsn, autocommit=False)
    return psycopg.connect(dsn)


def step(name: str):
    print(f"\n── {name} ─────────────────────────────────────────────")


def main():
    args = parse_args()
    src = connect(args.src)
    dst = connect(args.dst)
    src_cur = src.cursor()
    dst_cur = dst.cursor()

    try:
        # ── 1. auth.users ────────────────────────────────────────────────
        step("auth.users")
        src_cur.execute("SELECT user_id, role, created_at, updated_at FROM auth.users")
        users = src_cur.fetchall()
        print(f"  source rows: {len(users)}")
        if not args.dry_run:
            dst_cur.executemany(
                "INSERT INTO auth.users (user_id, role, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
                users,
            )

        # ── 2. gdpr.user_info (merge auth.gdpr + public.user_info) ───────
        step("gdpr.user_info (merge auth.gdpr ⨝ public.user_info)")
        src_cur.execute(
            "SELECT g.user_id, g.email, COALESCE(ui.user_name, ''), "
            "COALESCE(ui.config, '{}'::jsonb) "
            "FROM auth.gdpr g LEFT JOIN public.user_info ui USING (user_id)"
        )
        merged = src_cur.fetchall()
        print(f"  merged rows: {len(merged)}")
        if not args.dry_run:
            # Old user_name field had legacy values (handles, emails) that may
            # not match the new check_constraint regex ^[a-z0-9][a-z0-9_-]{2,31}$.
            # Coerce: lower, replace invalid chars with '-', truncate to 32, fall
            # back to 'user-' + first 8 of user_id when result is empty.
            import re
            cleaned = []
            for uid, email, uname, cfg in merged:
                u = (uname or "").lower()
                u = re.sub(r"[^a-z0-9_-]", "-", u)
                u = u.strip("-")[:32]
                if not re.match(r"^[a-z0-9][a-z0-9_-]{2,31}$", u):
                    u = f"user-{str(uid).replace('-', '')[:8]}"
                cleaned.append((uid, email, u, json.dumps(cfg)))
            dst_cur.executemany(
                "INSERT INTO gdpr.user_info (user_id, email, user_name, config) "
                "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (user_id) DO NOTHING",
                cleaned,
            )

        # ── 3. workspaces ────────────────────────────────────────────────
        step("public.workspaces")
        src_cur.execute(
            "SELECT workspace_id, workspace_name, created_at, updated_at FROM public.workspaces"
        )
        ws = src_cur.fetchall()
        print(f"  source rows: {len(ws)}")
        if not args.dry_run:
            dst_cur.executemany(
                "INSERT INTO public.workspaces "
                "(workspace_id, workspace_name, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (workspace_id) DO NOTHING",
                ws,
            )

        # ── 4. workspace_members ─────────────────────────────────────────
        step("public.workspace_members")
        src_cur.execute(
            "SELECT workspace_id, user_id, role FROM public.workspace_members"
        )
        wm = src_cur.fetchall()
        print(f"  source rows: {len(wm)}")
        if not args.dry_run:
            dst_cur.executemany(
                "INSERT INTO public.workspace_members (workspace_id, user_id, role) "
                "VALUES (%s, %s, %s) ON CONFLICT (workspace_id, user_id) DO NOTHING",
                wm,
            )

        # ── 5. tables + table_schemas + table_views (per-table loop) ─────
        step("tables / table_schemas / table_views (per-table)")
        src_cur.execute(
            "SELECT workspace_id, table_id, created_at, updated_at FROM public.tables"
        )
        tbls = src_cur.fetchall()
        print(f"  source tables: {len(tbls)}")

        total_schemas = 0
        total_views = 0
        for ws_id, tid, ca, ua in tbls:
            # 5a. insert the table row (trigger auto-inserts empty schema row)
            if not args.dry_run:
                dst_cur.execute(
                    "INSERT INTO public.tables (workspace_id, table_id, created_at, updated_at) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (workspace_id, table_id) DO NOTHING",
                    (ws_id, tid, ca, ua),
                )

            # 5b. pull old view rows for this table
            src_cur.execute(
                "SELECT name, type, config FROM public.table_views "
                "WHERE workspace_id=%s AND table_id=%s",
                (ws_id, tid),
            )
            old_views = src_cur.fetchall()
            schema_row = next(((n, t, c) for n, t, c in old_views if n == "__schema__"), None)
            order_row = next(((n, t, c) for n, t, c in old_views if n == "__order__"), None)
            user_views = [(n, t, c) for n, t, c in old_views if n not in ("__schema__", "__order__")]

            # 5c. insert each user view, capture new view_id
            name_to_view_id: dict[str, int] = {}
            for name, vtype, cfg in user_views:
                new_cfg = {**(cfg if isinstance(cfg, dict) else {}), "name": name, "type": vtype}
                if not args.dry_run:
                    dst_cur.execute(
                        "INSERT INTO public.table_views "
                        "(workspace_id, table_id, config) VALUES (%s, %s, %s::jsonb) "
                        "RETURNING view_id",
                        (ws_id, tid, json.dumps(new_cfg)),
                    )
                    new_view_id = dst_cur.fetchone()[0]
                    name_to_view_id[name] = new_view_id
                total_views += 1

            # 5d. build columns array + view_order, overwrite table_schemas
            columns = []
            if schema_row:
                _, _, sc = schema_row
                if isinstance(sc, dict):
                    columns = sc.get("columns", []) or []

            view_order: list[int] = []
            if order_row:
                _, _, oc = order_row
                if isinstance(oc, list):
                    view_order = [name_to_view_id[n] for n in oc if n in name_to_view_id]

            default_view = view_order[0] if view_order else None
            schema_cfg = {
                "columns": columns,
                "view_order": view_order,
                "default_view": default_view,
            }
            if not args.dry_run:
                dst_cur.execute(
                    "UPDATE public.table_schemas SET config=%s::jsonb, updated_at=now() "
                    "WHERE workspace_id=%s AND table_id=%s",
                    (json.dumps(schema_cfg), ws_id, tid),
                )
            total_schemas += 1

        print(f"  schemas written: {total_schemas}")
        print(f"  user views written: {total_views}")

        # ── 6. rows (row_number → row_id) ────────────────────────────────
        step("public.rows (row_number → row_id)")
        src_cur.execute(
            "SELECT workspace_id, table_id, row_number, row_data, "
            "created_by, updated_by, created_at, updated_at "
            "FROM public.rows"
        )
        rows = src_cur.fetchall()
        print(f"  source rows: {len(rows)}")
        if not args.dry_run:
            payload = [
                (ws, t, rn, json.dumps(rd), cb, ub, ca, ua)
                for ws, t, rn, rd, cb, ub, ca, ua in rows
            ]
            # row_id non-zero → BEFORE INSERT trigger leaves it alone.
            dst_cur.executemany(
                "INSERT INTO public.rows "
                "(workspace_id, table_id, row_id, row_data, created_by, updated_by, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s) "
                "ON CONFLICT (workspace_id, table_id, row_id) DO NOTHING",
                payload,
            )

        if args.dry_run:
            print("\n[DRY RUN] no writes — rolling back.")
            dst.rollback()
        else:
            dst.commit()
            print("\n✅ committed.")

    except Exception as e:  # noqa: BLE001
        dst.rollback()
        print(f"\n❌ rolled back: {e}", file=sys.stderr)
        raise
    finally:
        src_cur.close()
        dst_cur.close()
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
