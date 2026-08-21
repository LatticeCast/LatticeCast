-- Self-service operations derive their subject from app.current_user_id.
-- The backend supplies authentication context once; PostgreSQL owns identity
-- binding for workspace creation, sidebar reads, password changes, and DDL.

-- ── Password self-service ────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.get_current_user_password_hash()
RETURNS VARCHAR
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, gdpr, pg_temp
AS $$
DECLARE
    v_user_id UUID;
    v_hash    VARCHAR;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'authenticated user context required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    SELECT password_hash
    INTO   v_hash
    FROM   gdpr.user_password
    WHERE  user_id = v_user_id;

    RETURN v_hash;
END;
$$;

CREATE OR REPLACE FUNCTION public.set_current_user_password_hash(
    p_password_hash VARCHAR
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, gdpr, pg_temp
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'authenticated user context required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_password_hash IS NULL OR p_password_hash = '' THEN
        RAISE EXCEPTION 'password hash is required'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    INSERT INTO gdpr.user_password (user_id, password_hash)
    VALUES (v_user_id, p_password_hash)
    ON CONFLICT (user_id) DO UPDATE
    SET    password_hash = EXCLUDED.password_hash,
           updated_at    = now();
END;
$$;

REVOKE ALL ON FUNCTION public.get_current_user_password_hash() FROM public;
REVOKE ALL ON FUNCTION public.set_current_user_password_hash(VARCHAR) FROM public;
GRANT EXECUTE ON FUNCTION public.get_current_user_password_hash() TO app;
GRANT EXECUTE ON FUNCTION public.set_current_user_password_hash(VARCHAR) TO app;

-- ── Workspace creation and sidebar identity binding ───────────────────────

DROP FUNCTION IF EXISTS public.create_workspace(VARCHAR, UUID);

CREATE OR REPLACE FUNCTION public.create_workspace(
    p_workspace_name VARCHAR
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_workspace_id UUID;
    v_user_id      UUID;
    v_now          TIMESTAMP;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'authenticated user context required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO public.workspaces (workspace_name)
    VALUES (p_workspace_name)
    RETURNING workspace_id, created_at INTO v_workspace_id, v_now;

    INSERT INTO public.workspace_members (workspace_id, user_id, action)
    VALUES (v_workspace_id, v_user_id, 'read'),
           (v_workspace_id, v_user_id, 'write'),
           (v_workspace_id, v_user_id, 'owner');

    RETURN jsonb_build_object(
        'workspace_id',   v_workspace_id,
        'workspace_name', p_workspace_name,
        'created_at',     v_now,
        'updated_at',     v_now
    );
END;
$$;

REVOKE ALL ON FUNCTION public.create_workspace(VARCHAR) FROM public;
GRANT EXECUTE ON FUNCTION public.create_workspace(VARCHAR) TO app;

DROP FUNCTION IF EXISTS public.get_user_sidebar(UUID);

CREATE OR REPLACE FUNCTION public.get_user_sidebar()
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_user_id UUID;
BEGIN
    v_user_id := (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID;
    IF v_user_id IS NULL THEN
        RAISE EXCEPTION 'authenticated user context required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN jsonb_build_object(
        'workspaces', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id',   workspace.workspace_id,
                    'workspace_name', workspace.workspace_name
                )
                ORDER BY workspace.workspace_name
            )
            FROM public.workspaces AS workspace
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members AS member
                WHERE member.workspace_id = workspace.workspace_id
                  AND member.user_id = v_user_id
            )
        ), '[]'::JSONB),
        'tables', coalesce((
            SELECT jsonb_agg(
                jsonb_build_object(
                    'workspace_id', table_data.workspace_id,
                    'table_id',     table_data.table_id,
                    'config',       table_data.config
                )
                ORDER BY table_data.workspace_id, table_data.table_id
            )
            FROM public.tables AS table_data
            WHERE EXISTS (
                SELECT 1
                FROM public.workspace_members AS member
                WHERE member.workspace_id = table_data.workspace_id
                  AND member.user_id = v_user_id
            )
        ), '[]'::JSONB)
    );
END;
$$;

REVOKE ALL ON FUNCTION public.get_user_sidebar() FROM public;
GRANT EXECUTE ON FUNCTION public.get_user_sidebar() TO app;
