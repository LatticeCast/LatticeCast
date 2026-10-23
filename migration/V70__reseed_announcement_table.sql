-- upgrade
-- Re-seed the announcement table against the new identity.
--
-- V36 runs long before the cutover, so on a fresh database it creates the
-- announcement table in the old slug-keyed schema and V66 then archives that
-- copy into tables_old. The new public.tables therefore starts empty on a
-- fresh install, and the frontend's hard-coded `table("announcement")` query
-- would resolve to nothing.
--
-- Written against the relations rather than through create_table_from_template
-- and add_column: those authorise a session user (app.current_user_id), and a
-- migration has none. The system seed is a migration's business, so it writes
-- the same shape those functions would, including the per-column indexes.
--
-- Idempotent by design: on a cutover database the move script has already
-- carried the live announcement table across, so every step here is a no-op
-- unless something is missing.

DO $$
DECLARE
    v_announcement_user_id UUID := '36baf5e2-b9ae-4ef6-9657-3445a323128c';
    v_announcement_workspace_id UUID := 'f8bb8500-10f2-4e8c-b0a3-0d5c30778086';
    v_table_id BIGINT;
    v_config JSONB;
    v_column JSONB;
    v_idx_name TEXT;
BEGIN
    INSERT INTO auth.users (user_id)
    VALUES (v_announcement_user_id)
    ON CONFLICT (user_id) DO NOTHING;

    INSERT INTO gdpr.user_info (user_id, email, user_name)
    VALUES (
        v_announcement_user_id,
        'announcement@latticecast.local',
        'announcement'
    )
    ON CONFLICT (user_id) DO NOTHING;

    INSERT INTO public.workspaces (workspace_id, workspace_name)
    VALUES (v_announcement_workspace_id, 'announcement')
    ON CONFLICT (workspace_id) DO NOTHING;

    SELECT table_data.table_id
    INTO   v_table_id
    FROM   public.tables AS table_data
    WHERE  table_data.workspace_id = v_announcement_workspace_id
    AND    table_data.table_name = 'announcement';

    IF v_table_id IS NULL THEN
        -- Copy the archived definition when there is one: V36 ran before the
        -- cutover, so every database -- fresh install and migration alike --
        -- has the announcement table in tables_old with its own column ids.
        -- Reusing them keeps the rows the move script copies next keyed to
        -- columns that actually exist.
        SELECT old.config
        INTO   v_config
        FROM   public.tables_old AS old
        WHERE  old.workspace_id = v_announcement_workspace_id
        AND    old.table_id = 'announcement';

        IF v_config IS NULL THEN
            -- No archive (already cut over by hand): rebuild the shape V36 and
            -- V38 leave behind.
            v_config := jsonb_build_object(
            'columns', jsonb_build_array(
                public._build_column_dict('Title', 'text', '{}'::JSONB),
                public._build_column_dict('Description', 'text', '{}'::JSONB),
                public._build_column_dict(
                    'Type',
                    'select',
                    '{"choices":[
                        {"value":"server","color":"#60a5fa"},
                        {"value":"app","color":"#4ade80"}
                    ]}'::JSONB
                ),
                public._build_column_dict('updated_at', 'date', '{}'::JSONB),
                public._build_column_dict('updated_by', 'text', '{}'::JSONB),
                public._build_column_dict('created_at', 'date', '{}'::JSONB),
                public._build_column_dict('created_by', 'text', '{}'::JSONB)
            ),
            'view_order', '[]'::JSONB,
            'default_view', NULL::JSONB
            );
        END IF;

        INSERT INTO public.tables (
            workspace_id, table_name, config, created_by, updated_by
        ) VALUES (
            v_announcement_workspace_id,
            'announcement',
            v_config,
            v_announcement_user_id,
            v_announcement_user_id
        ) RETURNING table_id INTO v_table_id;
    ELSE
        SELECT table_data.config
        INTO   v_config
        FROM   public.tables AS table_data
        WHERE  table_data.table_id = v_table_id;
    END IF;

    -- CREATE INDEX IF NOT EXISTS inside, so a table that came across with the
    -- move script keeps the indexes the script built.
    FOR v_column IN SELECT * FROM jsonb_array_elements(v_config -> 'columns') LOOP
        IF v_column ->> 'type' IN (
            'number', 'date', 'datetime', 'text', 'string', 'select', 'tags',
            'email', 'url', 'phone', 'checkbox'
        ) THEN
            v_idx_name := public._build_rd_idx_name(
                v_announcement_workspace_id,
                v_table_id,
                v_column ->> 'column_id'
            );
            PERFORM public._create_row_data_index_unchecked(
                v_announcement_workspace_id,
                v_idx_name,
                v_table_id,
                v_column ->> 'column_id',
                v_column ->> 'type'
            );
        END IF;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM public.table_views
        WHERE table_id = v_table_id
          AND config ->> 'name' = 'announcement'
    ) THEN
        INSERT INTO public.table_views (
            workspace_id, table_id, config, created_by, updated_by
        ) VALUES (
            v_announcement_workspace_id,
            v_table_id,
            '{"name":"announcement","type":"table"}'::JSONB,
            v_announcement_user_id,
            v_announcement_user_id
        );
    END IF;

    INSERT INTO public.workspace_members (workspace_id, user_id, action)
    VALUES (
        v_announcement_workspace_id,
        v_announcement_user_id,
        'read'
    )
    ON CONFLICT (workspace_id, user_id, action) DO NOTHING;
END;
$$;
