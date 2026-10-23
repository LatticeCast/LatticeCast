#!/usr/bin/env python3
"""Move the pre-cutover table storage into the identity-keyed tables.

V66 renamed the old storage to *_old, V67/V68 created the empty replacements;
this script copies the data across and rebuilds the per-column row indexes:
they are derived state, and the copy is the only place that can build them for
the new table ids.

Why a script and not a migration: loading rows and using the result are two
different claims. This runs as a separate step so a failed copy leaves the
schema and the archive untouched, and so it can be re-run.

  python move_table_storage.py --apply     # copy, verify, commit — in that order
  python move_table_storage.py --verify    # compare archive vs new tables

The copy and the verification share one transaction: --apply commits only
after the archive has been read back and matched, so a disagreement rolls the
whole move back instead of leaving half-migrated data behind.

Idempotent: an archived row that differs from its copy is re-applied (the
archive wins), rows that already match are left alone, counters use GREATEST.
Re-running after a partial failure finishes the job and converges on the
archive instead of duplicating it.

Verification is by content, not by count. It fails when an archived table,
row, view, counter, or blob object is missing from the new storage or differs
from it; anything the new storage has that the archive does not is reported as
a total only, because rows created after cutover are legitimate and are not
the archive's business.

DSN comes from DATABASE_URL. Exit code is non-zero if verification disagrees.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2

MAPPING = "_move_table_map"

COPY_TABLES = f"""
CREATE TEMP TABLE IF NOT EXISTS {MAPPING} ON COMMIT DROP AS
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
    table_id, row_id, row_data, created_by, updated_by,
    created_at, updated_at
)
SELECT
    map.new_table_id, old.row_id, old.row_data,
    old.created_by, old.updated_by, old.created_at, old.updated_at
FROM public.rows_old AS old
JOIN {MAPPING} AS map
  ON  map.workspace_id  = old.workspace_id
  AND map.old_table_id  = old.table_id
ON CONFLICT (table_id, row_id) DO UPDATE
SET row_data   = excluded.row_data,
    created_by = excluded.created_by,
    updated_by = excluded.updated_by,
    created_at = excluded.created_at,
    updated_at = excluded.updated_at
-- The archive is the source of truth for the move: a wrong earlier copy is
-- corrected here instead of being left in place, and a matching row is not
-- rewritten (the row trigger would re-queue its blob objects).
WHERE public.rows.row_data   IS DISTINCT FROM excluded.row_data
   OR public.rows.created_by IS DISTINCT FROM excluded.created_by
   OR public.rows.updated_by IS DISTINCT FROM excluded.updated_by
   OR public.rows.created_at IS DISTINCT FROM excluded.created_at
   OR public.rows.updated_at IS DISTINCT FROM excluded.updated_at
"""

INSERT_VIEWS = f"""
INSERT INTO public.table_views (
    table_id, view_id, config, created_by, updated_by,
    created_at, updated_at
)
SELECT
    map.new_table_id, old.view_id, old.config,
    old.created_by, old.updated_by, old.created_at, old.updated_at
FROM public.table_views_old AS old
JOIN {MAPPING} AS map
  ON  map.workspace_id  = old.workspace_id
  AND map.old_table_id  = old.table_id
-- DO NOTHING let a seeded view with the same (table_id, view_id) keep its
-- simplified config while the row count still matched. The archive wins.
ON CONFLICT (table_id, view_id) DO UPDATE
SET config     = excluded.config,
    created_by = excluded.created_by,
    updated_by = excluded.updated_by,
    created_at = excluded.created_at,
    updated_at = excluded.updated_at
"""

# V70 seeds a placeholder announcement view before the move runs, so on a
# cutover database its view_id can differ from the archived one and the copy
# would leave both. The seed is a migration artefact, not user data — but only
# the row V70 itself created may be dropped, so the delete is bound to that
# migration's own transaction: created_at is the instant recorded in
# schema_migrations.applied_at, which no user view can carry. Everything else
# (a view a user added with the same config) is left alone and reported by the
# totals instead.
DELETE_SEEDED_VIEWS = f"""
DELETE FROM public.table_views AS seeded
USING private.schema_migrations AS applied
WHERE applied.filename = 'V70__reseed_announcement_table.sql'
  AND seeded.created_at = applied.applied_at
  AND seeded.config = '{{"name": "announcement", "type": "table"}}'::JSONB
  AND EXISTS (
      SELECT 1 FROM {MAPPING} AS map
      WHERE map.new_table_id = seeded.table_id
  )
  AND NOT EXISTS (
      SELECT 1
      FROM public.table_views_old AS old
      JOIN {MAPPING} AS map
        ON  map.workspace_id = old.workspace_id
        AND map.old_table_id = old.table_id
      WHERE map.new_table_id = seeded.table_id
        AND old.view_id      = seeded.view_id
  )
"""

# The row trigger already raised counters for the rows inserted above; GREATEST
# keeps the archived high-water mark so a deleted tail can never hand a row_id
# back out.
INSERT_COUNTERS = f"""
INSERT INTO private.table_row_counters (table_id, last_row_id)
SELECT map.new_table_id, old.last_row_id
FROM private.table_row_counters_old AS old
JOIN {MAPPING} AS map
  ON  map.workspace_id  = old.workspace_id
  AND map.old_table_id  = old.table_id
ON CONFLICT (table_id) DO UPDATE
SET last_row_id = greatest(
        private.table_row_counters.last_row_id,
        excluded.last_row_id
    )
"""

INSERT_BLOBS = f"""
INSERT INTO private.blob_objects (
    object_key, table_id, row_id, column_id
)
SELECT
    old.object_key, map.new_table_id, old.row_id, old.column_id
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

# ── Verification ────────────────────────────────────────────────────────────
# One row per claim; a claim with a non-zero count fails the run. The archive
# is always the reference: every archived value must exist in the new storage
# unchanged.

CHECKS = f"""
WITH
unmapped_tables AS (
    -- Read straight from the archive, never from the mapping: a table with no
    -- counterpart produces no mapping row, so a check that walks the mapping
    -- would silently skip the very table that failed to move.
    SELECT count(*) AS n
    FROM public.tables_old AS old
    WHERE NOT EXISTS (
        SELECT 1 FROM public.tables AS new
        WHERE new.workspace_id = old.workspace_id
          AND new.table_name   = old.table_id
    )
),
row_drift AS (
    SELECT count(*) AS n
    FROM public.rows_old AS old
    JOIN {MAPPING} AS map
      ON  map.workspace_id = old.workspace_id
      AND map.old_table_id = old.table_id
    LEFT JOIN public.rows AS new
      ON  new.table_id = map.new_table_id
      AND new.row_id   = old.row_id
    WHERE new.row_id IS NULL
       OR new.row_data   IS DISTINCT FROM old.row_data
       OR new.created_by IS DISTINCT FROM old.created_by
       OR new.updated_by IS DISTINCT FROM old.updated_by
       OR new.created_at IS DISTINCT FROM old.created_at
       OR new.updated_at IS DISTINCT FROM old.updated_at
),
view_drift AS (
    SELECT count(*) AS n
    FROM public.table_views_old AS old
    JOIN {MAPPING} AS map
      ON  map.workspace_id = old.workspace_id
      AND map.old_table_id = old.table_id
    LEFT JOIN public.table_views AS new
      ON  new.table_id = map.new_table_id
      AND new.view_id  = old.view_id
    WHERE new.view_id IS NULL
       OR new.config IS DISTINCT FROM old.config
),
counter_drift AS (
    SELECT count(*) AS n
    FROM private.table_row_counters_old AS old
    JOIN {MAPPING} AS map
      ON  map.workspace_id = old.workspace_id
      AND map.old_table_id = old.table_id
    LEFT JOIN private.table_row_counters AS new
      ON  new.table_id = map.new_table_id
    -- Rows added after cutover may raise the mark; it must never fall below
    -- the archived high-water mark.
    WHERE new.last_row_id IS NULL
       OR new.last_row_id < old.last_row_id
),
blob_drift AS (
    SELECT count(*) AS n
    FROM private.blob_objects_old AS old
    JOIN {MAPPING} AS map
      ON  map.workspace_id = old.workspace_id
      AND map.old_table_id = old.table_id
    LEFT JOIN private.blob_objects AS new
      ON  new.object_key = old.object_key
     AND  new.table_id   = map.new_table_id
     AND  new.row_id     = old.row_id
     AND  new.column_id  = old.column_id
    WHERE new.object_key IS NULL
)
SELECT 'archived tables without a copy'    AS claim, n, n > 0 AS broken
FROM unmapped_tables
UNION ALL SELECT 'row content/identity drift', n, n > 0 FROM row_drift
UNION ALL SELECT 'view config drift',          n, n > 0 FROM view_drift
UNION ALL SELECT 'row-id counter drift',       n, n > 0 FROM counter_drift
UNION ALL SELECT 'blob ownership missing',     n, n > 0 FROM blob_drift
"""

# Totals are context, not a verdict: rows or views created after cutover are
# expected to make the new side bigger.
TOTALS = f"""
SELECT 'tables', (SELECT count(*) FROM public.tables_old),
                 (SELECT count(*) FROM public.tables)
UNION ALL SELECT 'rows',
    (SELECT count(*) FROM public.rows_old),
    (SELECT count(*) FROM public.rows AS new
     JOIN {MAPPING} AS map ON map.new_table_id = new.table_id)
UNION ALL SELECT 'views',
    (SELECT count(*) FROM public.table_views_old),
    (SELECT count(*) FROM public.table_views AS new
     JOIN {MAPPING} AS map ON map.new_table_id = new.table_id)
UNION ALL SELECT 'blobs',
    (SELECT count(*) FROM private.blob_objects_old),
    (SELECT count(*) FROM private.blob_objects)
UNION ALL SELECT 'counters',
    (SELECT count(*) FROM private.table_row_counters_old),
    (SELECT count(*) FROM private.table_row_counters)
"""


def apply(conn) -> None:
    """Copy inside the caller's transaction; the caller commits or rolls back."""
    with conn.cursor() as cur:
        cur.execute(INSERT_TABLES)
        print(f"tables copied: {cur.rowcount}")
        cur.execute(COPY_TABLES)
        cur.execute(f"SELECT count(*) FROM {MAPPING}")
        print(f"mapped table ids: {cur.fetchone()[0]}")
        cur.execute(INSERT_ROWS)
        print(f"rows copied:   {cur.rowcount}")
        cur.execute(DELETE_SEEDED_VIEWS)
        if cur.rowcount:
            print(f"seeded views dropped: {cur.rowcount}")
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
        # --verify runs without apply(), so the mapping has to be built here.
        cur.execute(COPY_TABLES)
        cur.execute(TOTALS)
        for name, archived, current in cur.fetchall():
            print(f"{name:<12} archive={archived!s:<10} new={current!s:<10}")
        cur.execute(CHECKS)
        for claim, count, broken in cur.fetchall():
            state = "FAIL" if broken else "ok"
            if broken:
                ok = False
            print(f"{claim:<32} {count!s:<8} {state}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="copy, verify, then commit")
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
        if args.verify:
            conn.rollback()  # read-only run still needs a transaction snapshot
            return 0 if verify(conn) else 1

        apply(conn)
        if not verify(conn):
            conn.rollback()
            print("verification disagreed — nothing was committed", file=sys.stderr)
            return 1
        conn.commit()
        print("committed")
        return 0
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
