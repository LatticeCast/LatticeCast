-- upgrade
-- Allocate rows.row_id atomically.
--
-- V7's BEFORE INSERT trigger reads COALESCE(MAX(row_id), 0) + 1 from
-- public.rows. Under READ COMMITTED two concurrent inserts into the
-- same (workspace_id, table_id) cannot see each other's uncommitted
-- row, so both compute the same next id and one dies on the
-- (workspace_id, table_id, row_id) primary key. The failure mode is a
-- primary key violation surfaced to the client, not a retry and not
-- serialisation.
--
-- The race is not the deeper defect though. MAX+1 does not produce an
-- identifier at all, it produces an array index: unique only among the
-- rows that currently exist, and handed back out as soon as the tail is
-- removed. Everything downstream treats row_id as an identity --
-- storage keys ({workspace_id}/{table_id}/rows/{row_id}/blobs/...), PM
-- ticket keys derived from type + row_id, the Parent column, hive
-- branch names (story/story-5) and commit subjects (task-42: ...). A
-- reused number silently points a new ticket at a deleted one's
-- documents.
--
-- So reuse defeats the only thing a small integer key is for. If
-- row_id were not meant to be traceable there would be no reason to
-- keep it: a row_uuid ordered by created_at would do. It is kept
-- because humans say these numbers out loud and type them into
-- branches, and that only works if a number means one row forever.
--
-- Fix: one counter row per table, incremented by a single atomic
-- UPSERT, so row_id is monotonic per table.
--
-- Per table, not a global sequence, because the uniqueness scope is
-- per table: the primary key is (workspace_id, table_id, row_id), and
-- keeping the counter's scope equal to the key's scope is what lets
-- two tables allocate concurrently without touching the same row.
-- That composite key is also why workspace_id leads it -- the RLS
-- predicate filters on workspace_id, so authorisation rides the
-- primary key index instead of filtering after a heap read, and the
-- per-column row_data partial indexes share the same prefix.
--
-- Honest cost: the counter is derived state, and MAX+1 was not. MAX+1
-- could never disagree with the table because the table was its only
-- source. A counter can fall behind -- an explicit row_id (handled
-- below) or a load that bypasses triggers, such as pg_restore
-- --disable-triggers -- and falling behind means a hard primary key
-- collision rather than a wrong answer. migrate.py --dump is safe: it
-- clones with CREATE DATABASE WITH TEMPLATE, which copies the counter
-- along with the rows.
--
-- No gaps, unlike a sequence. nextval() is non-transactional and keeps
-- a value it handed to a transaction that then rolled back; a counter
-- *row* is ordinary MVCC, so a rollback reverts it, and a concurrent
-- allocator was blocked on that row's lock anyway and re-reads the
-- reverted value once the first transaction resolves. The same applies
-- to a rejected insert: RLS INSERT policies are checked after BEFORE
-- triggers run, but the failed check aborts the statement and takes the
-- counter update with it.
--
-- Deliberately no permission check inside the allocator: it would have
-- to special-case the migration-time context that has no
-- app.current_user_id, which is exactly how V36 seeds the announcement
-- rows. Nothing is leaked by incrementing a counter -- the insert
-- itself is still governed by the rows RLS policy.
--
-- Accepted cost: contention. Concurrent inserts into one table
-- serialise on that table's counter row until commit; inserts into
-- different tables never contend. A bulk import held open in a single
-- long transaction therefore blocks other inserts to the same table
-- for its duration.
--
-- This is independent of V48-V50 (timestamp canonicalisation) and can
-- be applied or reverted on its own.

-- ── Counter table ───────────────────────────────────────────────────────
-- Lives in `private`: app has no USAGE there (V1), so the counter is
-- unreachable from an end-user session and needs no RLS policy of its
-- own. The FK carries ON UPDATE CASCADE for the same reason V30 added
-- it to rows and table_views -- table_id is part of the key, and a
-- rename without it would silently reset the counter to zero.

CREATE TABLE IF NOT EXISTS private.table_row_counters (
    workspace_id UUID    NOT NULL,
    table_id     VARCHAR NOT NULL,
    last_row_id  BIGINT  NOT NULL,
    PRIMARY KEY (workspace_id, table_id),
    FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id)
    ON DELETE CASCADE ON UPDATE CASCADE
);

-- ── Seed from existing rows (MUST precede the trigger swap) ─────────────
-- Without this the first insert after the migration finds no counter
-- row, allocates 1, and collides with the existing row_id 1. greatest()
-- means a re-run can only raise a counter, never hand back a number
-- that is already in use.

INSERT INTO private.table_row_counters (workspace_id, table_id, last_row_id)
SELECT
    table_data.workspace_id,
    table_data.table_id,
    coalesce(max(row_data.row_id), 0) AS last_row_id
FROM   public.tables AS table_data
LEFT JOIN public.rows AS row_data
    ON  table_data.workspace_id = row_data.workspace_id
    AND table_data.table_id     = row_data.table_id
GROUP  BY table_data.workspace_id, table_data.table_id
ON CONFLICT (workspace_id, table_id) DO UPDATE
SET last_row_id = greatest(
        private.table_row_counters.last_row_id,
        excluded.last_row_id
    );

-- ── Atomic allocator ────────────────────────────────────────────────────
-- SECURITY DEFINER so the trigger can reach `private` without granting
-- an end-user role any access to the counter table.

CREATE OR REPLACE FUNCTION public.trg_set_row_id_fn()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = private, public, pg_temp
AS $$
BEGIN
    IF NEW.row_id IS NULL OR NEW.row_id = 0 THEN
        INSERT INTO private.table_row_counters
            (workspace_id, table_id, last_row_id)
        VALUES (NEW.workspace_id, NEW.table_id, 1)
        ON CONFLICT (workspace_id, table_id) DO UPDATE
        SET last_row_id = private.table_row_counters.last_row_id + 1
        RETURNING last_row_id INTO NEW.row_id;
    ELSE
        -- An explicitly supplied row_id must still advance the
        -- high-water mark, or the counter stays behind and a later
        -- auto-allocation walks straight into the existing row's key.
        -- RowRepository.create() never supplies one, but V36 seeds rows
        -- directly and mgr tooling can too. GREATEST() so an explicit
        -- id lower than the mark cannot rewind it; a duplicate is still
        -- rejected by the rows primary key, which is the correct owner
        -- of that error.
        INSERT INTO private.table_row_counters
            (workspace_id, table_id, last_row_id)
        VALUES (NEW.workspace_id, NEW.table_id, NEW.row_id)
        ON CONFLICT (workspace_id, table_id) DO UPDATE
        SET last_row_id = greatest(
                private.table_row_counters.last_row_id,
                excluded.last_row_id
            );
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_rows_row_id ON public.rows;
CREATE TRIGGER trg_rows_row_id
BEFORE INSERT ON public.rows
FOR EACH ROW EXECUTE FUNCTION public.trg_set_row_id_fn();

REVOKE ALL    ON
    FUNCTION public.trg_set_row_id_fn() FROM public;
GRANT EXECUTE ON
    FUNCTION public.trg_set_row_id_fn() TO app, mgr;
