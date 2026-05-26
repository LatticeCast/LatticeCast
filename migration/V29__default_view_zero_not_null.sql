-- V29: default_view uses 0 (implicit Schema view) instead of NULL.
-- Backfill existing tables and update the PG function to coerce NULL → 0.

-- Backfill: set NULL default_view to 0
UPDATE public.tables
SET    config = jsonb_set(config, '{default_view}', '0')
WHERE  config->>'default_view' IS NULL
    OR config->'default_view' = 'null'::JSONB;

-- Recreate update_default_view to coerce NULL → 0
CREATE OR REPLACE FUNCTION public.update_default_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_view_id      BIGINT,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_vid     BIGINT := COALESCE(p_view_id, 0);
    v_exists  BOOLEAN;
    v_new_cfg JSONB;
BEGIN
    IF v_vid != 0 THEN
        SELECT EXISTS (
            SELECT 1
            FROM   public.table_views
            WHERE  workspace_id = p_workspace_id
            AND    table_id     = p_table_id
            AND    view_id      = v_vid
        ) INTO v_exists;
        IF NOT v_exists THEN
            RAISE EXCEPTION 'view_id not found: %', v_vid;
        END IF;
    END IF;

    UPDATE public.tables
    SET    config     = jsonb_set(config, '{default_view}', to_jsonb(v_vid)),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %', p_workspace_id, p_table_id;
    END IF;

    RETURN v_new_cfg;
END;
$$;
