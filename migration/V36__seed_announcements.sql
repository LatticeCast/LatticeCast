-- V36 — seed the read-only announcement LatticeCast data.
--
-- The fixed identity only receives a read action.  Table, column, and view
-- configuration are created through the normal LatticeCast functions so this
-- seed follows the same schema and index conventions as user-created data.

DO $$
DECLARE
    v_announcement_user_id UUID := '36baf5e2-b9ae-4ef6-9657-3445a323128c';
    v_announcement_workspace_id UUID := 'f8bb8500-10f2-4e8c-b0a3-0d5c30778086';
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

    IF NOT EXISTS (
        SELECT 1
        FROM public.tables
        WHERE workspace_id = v_announcement_workspace_id
          AND table_id = 'announcement'
    ) THEN
        PERFORM public.create_table_from_template(
            v_announcement_workspace_id,
            'announcement',
            'blank',
            v_announcement_user_id
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.tables AS t
        CROSS JOIN LATERAL jsonb_array_elements(t.config -> 'columns') AS c
        WHERE t.workspace_id = v_announcement_workspace_id
          AND t.table_id = 'announcement'
          AND c ->> 'name' = 'Type'
    ) THEN
        PERFORM public.add_column(
            v_announcement_workspace_id,
            'announcement',
            'Type',
            'select',
            '{"choices":[
                {"value":"server","color":"#60a5fa"},
                {"value":"app","color":"#4ade80"}
            ]}'::JSONB,
            v_announcement_user_id
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.tables AS t
        CROSS JOIN LATERAL jsonb_array_elements(t.config -> 'columns') AS c
        WHERE t.workspace_id = v_announcement_workspace_id
          AND t.table_id = 'announcement'
          AND c ->> 'name' = 'Time'
    ) THEN
        PERFORM public.add_column(
            v_announcement_workspace_id,
            'announcement',
            'Time',
            'date',
            '{}'::JSONB,
            v_announcement_user_id
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.table_views
        WHERE workspace_id = v_announcement_workspace_id
          AND table_id = 'announcement'
          AND config ->> 'name' = 'announcement'
    ) THEN
        PERFORM public.create_view(
            v_announcement_workspace_id,
            'announcement',
            '{"name":"announcement","type":"table"}'::JSONB,
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
