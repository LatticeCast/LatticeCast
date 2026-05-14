-- upgrade
-- V9 set table_views.view_id DEFAULT 1 with the intent that the BEFORE
-- INSERT trigger (trg_set_view_id_fn) would auto-assign a per-table
-- sequence. But the trigger only fires when view_id IS NULL OR = 0,
-- so the DEFAULT of 1 silently bypassed it and the second INSERT into
-- the same table_id collided on PK (view_id=1 already exists).
--
-- This migration:
--   1. Drops the DEFAULT so unspecified INSERTs leave view_id NULL,
--      which makes the trigger fire and assign MAX(view_id)+1.
--   2. Leaves the trigger condition untouched (still handles explicit
--      0 sentinel for callers that pass it).

ALTER TABLE public.table_views ALTER COLUMN view_id DROP DEFAULT;

-- Tighten the NOT NULL: the trigger runs BEFORE INSERT and always
-- assigns a value, so the constraint still holds even without a DEFAULT.
-- (No-op assertion; documenting intent.)
ALTER TABLE public.table_views ALTER COLUMN view_id SET NOT NULL;
