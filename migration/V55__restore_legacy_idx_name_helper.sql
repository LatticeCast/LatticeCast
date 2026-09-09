-- upgrade
-- Restore public._build_rd_idx_name(TEXT, TEXT).
--
-- V49 dropped it as dead surface. It is not dead: V47's
-- drop_row_data_index deliberately drops TWO indexes for a column -- the
-- workspace-scoped one it now creates, and the unscoped one any database
-- migrated before V47 still carries -- and it needs this two-argument
-- helper to reconstruct that older name:
--
--     v_legacy_idx_name := public._build_rd_idx_name(p_table_id, p_column_id);
--     EXECUTE format('DROP INDEX IF EXISTS public.%I', p_idx_name);
--     EXECUTE format('DROP INDEX IF EXISTS public.%I', v_legacy_idx_name);
--
-- So deleting any indexed column failed outright:
--
--     ERROR: function public._build_rd_idx_name(text, text) does not exist
--     QUERY: v_legacy_idx_name := public._build_rd_idx_name(p_table_id, ...)
--
-- V49's claim that "the active add_column / delete_column call the new
-- arities, so nothing reaches them" was checked with a query that returned
-- only the FIRST match per function body, which hid this second call inside
-- drop_row_data_index. regexp_matches(..., 'g') shows all of them.
--
-- Definition is V11's, unchanged. Grants are not: V11 gave it to app and
-- mgr, but the only caller is a SECURITY DEFINER function that runs as its
-- owner, so no end-user role needs EXECUTE on it.

CREATE OR REPLACE FUNCTION public._build_rd_idx_name(
    p_table_id  TEXT,
    p_column_id TEXT
) RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'idx_rd_'
        || regexp_replace(lower(p_table_id), '[^a-z0-9]', '', 'g')
        || '_'
        || left(replace(p_column_id, '-', ''), 12);
$$;

REVOKE ALL ON
    FUNCTION public._build_rd_idx_name(TEXT, TEXT) FROM public;
