-- V19: update_view — null-valued patch keys DELETE the key from config
-- instead of merging {"key": null} into the JSONB object.
--
-- Before: config || p_patch → {"sort": null, "filter": null, ...} accumulates nulls
-- After:  merge non-null keys, remove null-valued keys

CREATE OR REPLACE FUNCTION public.update_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_view_id      BIGINT,
    p_patch        JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_new_cfg JSONB;
    v_merged  JSONB;
    v_key     TEXT;
BEGIN
    -- Build merged config: start with existing, apply non-null patch keys,
    -- remove keys where patch value is JSON null.
    SELECT config INTO v_merged
    FROM   public.table_views
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    view_id      = p_view_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'view not found: %', p_view_id;
    END IF;

    FOR v_key IN SELECT key FROM jsonb_each(p_patch)
    LOOP
        IF (p_patch -> v_key) = 'null'::jsonb THEN
            v_merged := v_merged - v_key;
        ELSE
            v_merged := jsonb_set(v_merged, ARRAY[v_key], p_patch -> v_key);
        END IF;
    END LOOP;

    UPDATE public.table_views
    SET    config     = v_merged,
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    view_id      = p_view_id;

    SELECT config
    INTO   v_new_cfg
    FROM   public.table_schemas
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    RETURN v_new_cfg;
END;
$$;
