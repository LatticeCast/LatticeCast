-- upgrade
-- View CRUD. All three return the full public.table_schemas.config
-- ({columns, view_order, default_view}) so the FE replaces its local
-- schema cache from the response.
--
--   create_view(ws, tid, config, by)        → schemas.config
--   update_view(ws, tid, view_id, patch, by) → schemas.config
--   delete_view(ws, tid, view_id, by)       → schemas.config
--
-- create_view appends the new view_id to view_order atomically. The
-- BEFORE INSERT trigger trg_set_view_id assigns view_id from
-- COALESCE(MAX, 0) + 1 within (workspace_id, table_id).

-- ── create_view ─────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.create_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_config       JSONB,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_view_id BIGINT;
    v_new_cfg JSONB;
BEGIN
    INSERT INTO public.table_views (
        workspace_id, table_id, config, created_by, updated_by
    ) VALUES (
        p_workspace_id, p_table_id, p_config, p_by, p_by
    ) RETURNING view_id INTO v_view_id;

    UPDATE public.table_schemas
    SET    config = jsonb_set(
               config,
               '{view_order}',
               COALESCE(config -> 'view_order', '[]'::JSONB) || to_jsonb(v_view_id)
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;

-- ── update_view ─────────────────────────────────────────────────────────────
-- Patch is merged into the view's config JSONB. Returns the table_schemas
-- config (view_order/default_view unaffected by edits — view_id is
-- immutable).

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
BEGIN
    UPDATE public.table_views
    SET    config     = config || p_patch,
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    view_id      = p_view_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'view not found: %', p_view_id;
    END IF;

    SELECT config
    INTO   v_new_cfg
    FROM   public.table_schemas
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    RETURN v_new_cfg;
END;
$$;

-- ── delete_view ─────────────────────────────────────────────────────────────
-- Removes the view row, strips its view_id from view_order, and clears
-- default_view if it pointed here.

CREATE OR REPLACE FUNCTION public.delete_view(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_view_id      BIGINT,
    p_by           UUID
) RETURNS JSONB
LANGUAGE plpgsql
SET search_path = public, pg_temp
AS $$
DECLARE
    v_old_order   JSONB;
    v_new_order   JSONB;
    v_old_default JSONB;
    v_new_default JSONB;
    v_new_cfg     JSONB;
BEGIN
    DELETE FROM public.table_views
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    AND    view_id      = p_view_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'view not found: %', p_view_id;
    END IF;

    SELECT config -> 'view_order', config -> 'default_view'
    INTO   v_old_order, v_old_default
    FROM   public.table_schemas
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id;

    -- Strip view_id from view_order.
    SELECT COALESCE(jsonb_agg(x), '[]'::JSONB)
    INTO   v_new_order
    FROM   jsonb_array_elements(COALESCE(v_old_order, '[]'::JSONB)) AS x
    WHERE  (x)::TEXT::BIGINT <> p_view_id;

    -- Clear default_view if it pointed here.
    IF v_old_default IS NOT NULL
        AND v_old_default <> 'null'::JSONB
        AND (v_old_default)::TEXT::BIGINT = p_view_id
    THEN
        v_new_default := 'null'::JSONB;
    ELSE
        v_new_default := v_old_default;
    END IF;

    UPDATE public.table_schemas
    SET    config = jsonb_set(
               jsonb_set(config, '{view_order}', v_new_order),
               '{default_view}',
               COALESCE(v_new_default, 'null'::JSONB)
           ),
           updated_by = p_by,
           updated_at = now()
    WHERE  workspace_id = p_workspace_id
    AND    table_id     = p_table_id
    RETURNING config INTO v_new_cfg;

    RETURN v_new_cfg;
END;
$$;

-- ── Grants ──────────────────────────────────────────────────────────────────

REVOKE ALL    ON
    FUNCTION public.create_view(UUID, VARCHAR, JSONB, UUID)         FROM public;
REVOKE ALL    ON
    FUNCTION public.update_view(UUID, VARCHAR, BIGINT, JSONB, UUID) FROM public;
REVOKE ALL    ON
    FUNCTION public.delete_view(UUID, VARCHAR, BIGINT, UUID)        FROM public;

GRANT EXECUTE ON
    FUNCTION public.create_view(UUID, VARCHAR, JSONB, UUID)         TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.update_view(UUID, VARCHAR, BIGINT, JSONB, UUID) TO app, mgr;
GRANT EXECUTE ON
    FUNCTION public.delete_view(UUID, VARCHAR, BIGINT, UUID)        TO app, mgr;
