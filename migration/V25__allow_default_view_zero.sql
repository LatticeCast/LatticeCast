-- V25: Allow default_view=0 (implicit Schema view sentinel)
-- view_id=0 is a frontend-only concept, not stored in table_views.

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
    v_exists  BOOLEAN;
    v_new_cfg JSONB;
BEGIN
    IF p_view_id IS NOT NULL AND p_view_id != 0 THEN
        SELECT EXISTS (
            SELECT 1
            FROM   public.table_views
            WHERE  workspace_id = p_workspace_id
            AND    table_id     = p_table_id
            AND    view_id      = p_view_id
        ) INTO v_exists;
        IF NOT v_exists THEN
            RAISE EXCEPTION 'view_id not found: %',
                p_view_id;
        END IF;
    END IF;

    UPDATE public.tables
    SET    config     = jsonb_set(
               config,
               '{default_view}',
               COALESCE(to_jsonb(p_view_id), 'null'::JSONB)
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    IF v_new_cfg IS NULL THEN
        RAISE EXCEPTION 'table not found: %, %',
            p_workspace_id, p_table_id;
    END IF;

    RETURN v_new_cfg;
END;
$$;
