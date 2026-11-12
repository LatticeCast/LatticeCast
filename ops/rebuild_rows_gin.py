#!/usr/bin/env python3
"""Manual, staged switch to one (table_id, row_data) GIN index.

After backing up the database and applying V77, run --build, inspect --status
and the RLS query plans, then explicitly run --drop-old. Nothing in the
migration runner calls this script. Each index command is an independent
autocommit statement, so a partial run can be resumed. --drop-old removes
the old global GIN plus legacy per-column indexes for all non-range types,
including select, tags and checkbox. Number/date B-tree indexes remain for
range/sort. Removed columns' orphaned indexes are retired as well.

The new GIN supports table_id equality with JSONB @> containment. It does
not index arbitrary row_data numeric/date ranges or ordering. Review those
query costs before choosing --drop-old.
"""

from __future__ import annotations

import argparse
import os

import psycopg2
from psycopg2 import sql

NEW_INDEX = "idx_rows_table_data_gin"
OLD_INDEX = "idx_rows_row_data_gin"

LEGACY_INDEX_QUERY = """
WITH live_columns AS (
    SELECT public._build_rd_idx_name(
               t.workspace_id, t.table_id, c.value ->> 'column_id'
           ) AS index_name,
           c.value ->> 'type' AS column_type
    FROM public.tables AS t
    CROSS JOIN LATERAL jsonb_array_elements(t.config -> 'columns') AS c
)
SELECT idx.relname
FROM pg_class AS idx
JOIN pg_index AS ix ON ix.indexrelid = idx.oid
JOIN pg_class AS tbl ON tbl.oid = ix.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
JOIN pg_am AS am ON am.oid = idx.relam
LEFT JOIN live_columns AS col ON col.index_name = idx.relname
WHERE ns.nspname = 'public'
  AND tbl.relname = 'rows'
  AND idx.relname LIKE 'idx\\_rd\\_%' ESCAPE '\\'
  AND NOT ix.indisprimary
  AND NOT ix.indisunique
  AND (
      am.amname = 'gin'
      OR col.column_type IS NULL
      OR col.column_type NOT IN ('number', 'date', 'datetime')
  )
  AND NOT EXISTS (
      SELECT 1 FROM pg_constraint AS con WHERE con.conindid = idx.oid
  )
ORDER BY idx.relname
"""


def _index_state(cursor) -> tuple[bool, bool, str] | None:
    cursor.execute(
        "SELECT ix.indisvalid, ix.indisready, pg_get_indexdef(ix.indexrelid) "
        "FROM pg_index AS ix "
        "WHERE ix.indexrelid = to_regclass('public.idx_rows_table_data_gin') "
        "AND ix.indrelid = 'public.rows'::regclass"
    )
    return cursor.fetchone()


def _index_exists(cursor, name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM pg_class AS idx "
        "JOIN pg_namespace AS ns ON ns.oid = idx.relnamespace "
        "WHERE ns.nspname = 'public' AND idx.relname = %s AND idx.relkind = 'i'",
        (name,),
    )
    return cursor.fetchone() is not None


def _ready_new_index(cursor) -> bool:
    state = _index_state(cursor)
    return (
        state is not None
        and state[:2] == (True, True)
        and "USING gin (table_id, row_data jsonb_path_ops)" in state[2]
    )


def run(dsn: str, *, action: str, limit: int | None) -> int:
    connection = psycopg2.connect(dsn)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(LEGACY_INDEX_QUERY)
            names = [row[0] for row in cursor.fetchall()]
            if action == "status":
                print(f"New multicolumn GIN ready: {_ready_new_index(cursor)}")
                print(f"Old global GIN exists: {_index_exists(cursor, OLD_INDEX)}")
                print(f"Superseded per-column indexes: {len(names)}")
                return len(names)

            cursor.execute(
                "SELECT 1 FROM private.schema_migrations "
                "WHERE filename = 'V77__table_scoped_jsonb_gin.sql'"
            )
            if cursor.fetchone() is None:
                raise RuntimeError("Apply V77 before changing rows indexes")
            cursor.execute("SET lock_timeout = '5s'")
            if action == "build":
                cursor.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
                current = _index_state(cursor)
                if (
                    current is not None
                    and "USING gin (table_id, row_data jsonb_path_ops)"
                    not in current[2]
                ):
                    raise RuntimeError(
                        "Existing rows GIN name has an unexpected definition"
                    )
                if current is not None and current[:2] != (True, True):
                    cursor.execute(
                        sql.SQL("DROP INDEX CONCURRENTLY public.{}").format(
                            sql.Identifier(NEW_INDEX)
                        )
                    )
                cursor.execute(
                    sql.SQL(
                        "CREATE INDEX CONCURRENTLY IF NOT EXISTS {} "
                        "ON public.rows USING gin (table_id, row_data jsonb_path_ops)"
                    ).format(sql.Identifier(NEW_INDEX))
                )
                if not _ready_new_index(cursor):
                    raise RuntimeError(
                        "New rows GIN is not valid, ready, and correctly defined"
                    )
                print(
                    "New multicolumn GIN ready; old indexes remain for manual verification"
                )
                return len(names)

            if not _ready_new_index(cursor):
                raise RuntimeError(
                    "Build and verify the new multicolumn GIN before dropping old indexes"
                )
            if _index_exists(cursor, OLD_INDEX):
                cursor.execute(
                    sql.SQL("DROP INDEX CONCURRENTLY public.{}").format(
                        sql.Identifier(OLD_INDEX)
                    )
                )
            if limit is not None:
                names = names[:limit]
            for number, name in enumerate(names, 1):
                cursor.execute(
                    sql.SQL("DROP INDEX CONCURRENTLY IF EXISTS public.{}").format(
                        sql.Identifier(name)
                    )
                )
                if number % 100 == 0 or number == len(names):
                    print(
                        f"Dropped {number}/{len(names)} superseded indexes", flush=True
                    )
            return len(names)
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--build", action="store_true", help="build new GIN; leave old indexes in place"
    )
    actions.add_argument(
        "--drop-old", action="store_true", help="drop old GIN and per-column indexes"
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.limit is not None and not args.drop_old:
        parser.error("--limit applies only to --drop-old")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("DATABASE_URL must be set to the DBA DSN")
    action = "build" if args.build else "drop-old" if args.drop_old else "status"
    run(dsn, action=action, limit=args.limit)


if __name__ == "__main__":
    main()
