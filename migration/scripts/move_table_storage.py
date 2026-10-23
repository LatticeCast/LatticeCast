#!/usr/bin/env python3
"""Move the pre-cutover table storage into the identity-keyed tables.

V66 renamed the old storage to *_old, V67/V68 created the empty replacements;
this script copies the data across and rebuilds the per-column row indexes:
they are derived state, and the copy is the only place that can build them for
the new table ids.

Why a script and not a migration: loading rows and using the result are two
different claims. This runs as a separate step so a failed copy leaves the
schema and the archive untouched, and so it can be re-run.

  python move_table_storage.py --apply     # copy, then verify
  python move_table_storage.py --verify    # compare archive vs new tables

Idempotent: every insert is ON CONFLICT DO NOTHING (counters use GREATEST), so
re-running after a partial failure finishes the job instead of duplicating it.

DSN comes from DATABASE_URL. Exit code is non-zero if verification disagrees.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2

MAPPING = "_move_table_map"

COPY_TABLES = f"""
CREATE TEMP TABLE {MAPPING} ON COMMIT DROP AS
SELECT
    old.workspace_id,
    old.table_id AS old_table_id,
    new.table_id AS new_table_id
FROM public.tables_old AS old
JOIN public.tables AS new
  ON  new.workspace_id = old.workspace_id
  AND new.table_name   = old.table_id;
"""

INSERT_TABLES = f"""
WITH src AS (
    SELECT
        old.workspace_id,
        old.table_id,
        old.config,
        old.created_by,
        old.updated_by,
        old.created_at,
        old.updated_at
    FROM public.tables_old AS old
)
INSERT INTO public.tables (
    workspace_id, table_name, config, created_by, updated_by, created_at, updated_at
)
SELECT
    src.workspace_id, src.table_id, src.config,
    src.created_by, src.updated_by, src.created_at, src.updated_at
FROM src
-- NOT EXISTS rather than ON CONFLICT: nextval() is non-transactional, so a
-- conflicting row would still burn an identity value and leave a gap.
WHERE NOT EXISTS (
    SELECT 1 FROM public.tables AS existing
    WHERE existing.workspace_id = src.workspace_id
      AND existing.table_name   = src.table_id
)
"""

INSERT_ROWS = f"""
INSERT INTO public.rows (
    workspace_id, table_id, row_id, row_data, created_by, updated_by,
    created_at, updated_at
)
SELECT
    old.workspace_id, map.new_table_id, old.row_id, old.row_data,
    old.created_by, old.updated_by, old.created_at, old.updated_at
FROM public.rows_old AS old
JOIN {MAPPING} AS map
  ON  map.workspace_id  = old.workspace_id
  AND map.old_table_id  = old.table_id
ON CONFLICT (table_id, row_id) DO NOTHING
"""

INSERT_VIEWS = f"""
INSERT INTO public.table_views (
    workspace_id, table_id, view_id, config, created_by, updated_by,
    created_at, updated_at
)
SELECT
    old.workspace_id, map.new_table_id, old.view_id, old.config,
    old.created_by, old.updated_by, old.created_at, old.updated_at
FROM public.table_views_old AS old
JOIN {MAPPING} AS map
  ON  map.workspace_id  = old.workspace_id
  AND map.old_table_id  = old.table_id
ON CONFLICT (table_id, view_id) DO NOTHING
"""

# The row trigger already raised counters for the rows inserted above; GREATEST
# keeps the archived high-water mark so a deleted tail can never hand a row_id
# back out.
INSERT_COUNTERS = f"""
INSERT INTO private.table_row_counters (workspace_id, table_id, last_row_id)
SELECT old.workspace_id, map.new_table_id, old.last_row_id
FROM private.table_row_counters_old AS old
JOIN {MAPPING} AS map
  ON  map.workspace_id  = old.workspace_id
  AND map.old_table_id  = old.table_id
ON CONFLICT (workspace_id, table_id) DO UPDATE
SET last_row_id = greatest(
        private.table_row_counters.last_row_id,
        excluded.last_row_id
    )
"""

INSERT_BLOBS = f"""
INSERT INTO private.blob_objects (
    object_key, workspace_id, table_id, row_id, column_id
)
SELECT
    old.object_key, old.workspace_id, map.new_table_id, old.row_id, old.column_id
FROM private.blob_objects_old AS old
JOIN {MAPPING} AS map
  ON  map.workspace_id  = old.workspace_id
  AND map.old_table_id  = old.table_id
ON CONFLICT (object_key) DO NOTHING
"""

# Index names are derived from the new table id, so they are built here rather
# than carried over: the archive's names are keyed by the old slug.
REBUILD_INDEXES = f"""
DO $$
DECLARE
    entry RECORD;
BEGIN
    FOR entry IN
        SELECT
            table_data.workspace_id,
            table_data.table_id AS new_table_id,
            column_data ->> 'column_id' AS column_id,
            column_data ->> 'type'      AS column_type
        FROM public.tables AS table_data
        JOIN {MAPPING} AS map ON map.new_table_id = table_data.table_id
        CROSS JOIN LATERAL jsonb_array_elements(table_data.config -> 'columns')
            AS column_data
        WHERE column_data ->> 'type' IN (
            'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        )
    LOOP
        PERFORM public._create_row_data_index_unchecked(
            entry.workspace_id,
            public._build_rd_idx_name(
                entry.workspace_id, entry.new_table_id, entry.column_id
            ),
            entry.new_table_id,
            entry.column_id,
            entry.column_type
        );
    END LOOP;
END;
$$;
"""

VERIFY = """
SELECT 'tables', (SELECT count(*)::TEXT FROM public.tables_old),
                (SELECT count(*)::TEXT FROM public.tables)
UNION ALL SELECT 'rows', (SELECT count(*)::TEXT FROM public.rows_old),
                        (SELECT count(*)::TEXT FROM public.rows)
UNION ALL SELECT 'views', (SELECT count(*)::TEXT FROM public.table_views_old),
                         (SELECT count(*)::TEXT FROM public.table_views)
UNION ALL SELECT 'blobs', (SELECT count(*)::TEXT FROM private.blob_objects_old),
                         (SELECT count(*)::TEXT FROM private.blob_objects)
UNION ALL SELECT 'counters',
    (SELECT count(*)::TEXT FROM private.table_row_counters_old),
    (SELECT count(*)::TEXT FROM private.table_row_counters)
UNION ALL SELECT 'content_sha',
    (SELECT md5(coalesce(string_agg(
        row_data::TEXT, '' ORDER BY workspace_id, table_id, row_id
    ), '')) FROM public.rows_old),
    (SELECT md5(coalesce(string_agg(
        old.row_data::TEXT, '' ORDER BY old.workspace_id, old.table_id, old.row_id
    ), '')) FROM public.rows AS new
        JOIN public.tables AS t ON t.table_id = new.table_id
        JOIN public.rows_old AS old
          ON  old.workspace_id = new.workspace_id
          AND old.table_id     = t.table_name
          AND old.row_id       = new.row_id)
"""


def apply(conn) -> None:
    with conn, conn.cursor() as cur:
        cur.execute(INSERT_TABLES)
        print(f"tables copied: {cur.rowcount}")
        cur.execute(COPY_TABLES)
        cur.execute(f"SELECT count(*) FROM {MAPPING}")
        print(f"mapped table ids: {cur.fetchone()[0]}")
        cur.execute(INSERT_ROWS)
        print(f"rows copied:   {cur.rowcount}")
        cur.execute(INSERT_VIEWS)
        print(f"views copied:  {cur.rowcount}")
        cur.execute(INSERT_COUNTERS)
        print(f"counters:      {cur.rowcount}")
        cur.execute(INSERT_BLOBS)
        print(f"blobs copied:  {cur.rowcount}")
        cur.execute(REBUILD_INDEXES)
        print("per-column indexes rebuilt for the new table ids")


def verify(conn) -> bool:
    ok = True
    with conn.cursor() as cur:
        cur.execute(VERIFY)
        for name, archived, current in cur.fetchall():
            match = "ok" if archived == current else "MISMATCH"
            if archived != current:
                ok = False
            print(f"{name:<12} archive={archived!s:<10} new={current!s:<10} {match}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="copy, then verify")
    parser.add_argument("--verify", action="store_true", help="compare only")
    args = parser.parse_args()
    if not (args.apply or args.verify):
        parser.error("choose --apply or --verify")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    conn = psycopg2.connect(dsn)
    try:
        if args.apply:
            apply(conn)
        return 0 if verify(conn) else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
