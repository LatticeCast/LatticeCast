-- upgrade
-- Push "who can do what in a workspace" down into RLS via a generic
-- action-grant model, replacing the role column (owner/member) that
-- only ever gated app-layer checks (_require_owner in
-- router/api/workspaces.py) — RLS itself never looked at it, so any
-- member, owner or not, already had full read+write on a workspace's
-- data. This migration makes that distinction real at the DB layer.
--
-- workspace_members moves from one row per (workspace_id, user_id) to
-- possibly MULTIPLE rows — one per granted action ('read' / 'write' /
-- 'owner'). Owner is materialized as three rows (read + write + owner)
-- rather than encoded via hierarchy logic in the check function, so
-- every RLS check stays a flat equality lookup:
--   EXISTS(... WHERE workspace_id = X AND user_id = Y AND action = Z)
--
-- Two access patterns, no table needs all three:
--   workspace_members — single check, action = 'owner', for ALL
--     commands (SELECT included). Only owners can see or change the
--     member list; there is no read-only roster view.
--   workspaces / tables / rows / table_views — SELECT needs 'read',
--     INSERT/UPDATE/DELETE needs 'write'. workspaces additionally
--     restricts INSERT/UPDATE/DELETE to 'owner' (rename/delete were
--     already owner-only in application code — see _require_owner).
--
-- Backfill: every existing member currently has full read+write via
-- RLS regardless of role — so every existing row becomes read+write
-- rows, and existing role='owner' rows additionally get an owner row.

-- ── Backfill + schema change ─────────────────────────────────────────────

ALTER TABLE public.workspace_members ADD COLUMN IF NOT EXISTS action VARCHAR;
ALTER TABLE public.workspace_members DROP CONSTRAINT workspace_members_pkey;

-- Repurpose each existing row in place as its 'read' grant.
UPDATE public.workspace_members
SET    action = 'read'
WHERE  action IS NULL;

-- Everyone who had any row gets 'write' too (today's RLS gave every
-- member full read+write regardless of role).
INSERT INTO public.workspace_members (workspace_id, user_id, action)
SELECT
    workspace_id,
    user_id,
    'write' AS action
FROM   public.workspace_members
WHERE  action = 'read';

-- Prior owners additionally get 'owner'.
INSERT INTO public.workspace_members (workspace_id, user_id, action)
SELECT
    workspace_id,
    user_id,
    'owner' AS action
FROM   public.workspace_members
WHERE  action = 'read' AND role = 'owner';

ALTER TABLE public.workspace_members DROP COLUMN role;
ALTER TABLE public.workspace_members ALTER COLUMN action SET NOT NULL;

ALTER TABLE public.workspace_members
    ADD CONSTRAINT workspace_members_action_check
    CHECK (action IN ('read', 'write', 'owner'));

ALTER TABLE public.workspace_members
    ADD PRIMARY KEY (workspace_id, user_id, action);

-- ── Permission check function ───────────────────────────────────────────
-- SECURITY DEFINER for the same reason as the old check_workspace_member
-- (V10): the policy on workspace_members itself calls this function —
-- without SECURITY DEFINER the policy would recurse into itself.

CREATE OR REPLACE FUNCTION public.check_workspace_permission(
    ws_id    UUID,
    u_id     UUID,
    p_action VARCHAR
) RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM   public.workspace_members
        WHERE  workspace_id = ws_id
        AND    user_id      = u_id
        AND    action        = p_action
    );
$$;

REVOKE ALL    ON
    FUNCTION public.check_workspace_permission(UUID, UUID, VARCHAR) FROM public;
GRANT EXECUTE ON
    FUNCTION public.check_workspace_permission(UUID, UUID, VARCHAR) TO app, mgr;

-- ── RLS: workspace_members — owner only, every command ──────────────────

DROP POLICY IF EXISTS workspace_members_workspace_member ON public.workspace_members;
DROP POLICY IF EXISTS workspace_members_owner ON public.workspace_members;
CREATE POLICY workspace_members_owner ON public.workspace_members
USING (
    public.check_workspace_permission(
        workspace_id,
        (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID,
        'owner'
    )
);

-- ── RLS: workspaces — read to view, owner to mutate ──────────────────────

DROP POLICY IF EXISTS workspaces_workspace_member ON public.workspaces;

DROP POLICY IF EXISTS workspaces_read ON public.workspaces;
CREATE POLICY workspaces_read ON public.workspaces
FOR SELECT
USING (
    public.check_workspace_permission(
        workspace_id,
        (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID,
        'read'
    )
);

DROP POLICY IF EXISTS workspaces_owner_insert ON public.workspaces;
CREATE POLICY workspaces_owner_insert ON public.workspaces
FOR INSERT
WITH CHECK (
    public.check_workspace_permission(
        workspace_id,
        (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID,
        'owner'
    )
);

DROP POLICY IF EXISTS workspaces_owner_update ON public.workspaces;
CREATE POLICY workspaces_owner_update ON public.workspaces
FOR UPDATE
USING (
    public.check_workspace_permission(
        workspace_id,
        (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID,
        'owner'
    )
)
WITH CHECK (
    public.check_workspace_permission(
        workspace_id,
        (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID,
        'owner'
    )
);

DROP POLICY IF EXISTS workspaces_owner_delete ON public.workspaces;
CREATE POLICY workspaces_owner_delete ON public.workspaces
FOR DELETE
USING (
    public.check_workspace_permission(
        workspace_id,
        (nullif(current_setting('app.current_user_id', TRUE), ''))::UUID,
        'owner'
    )
);

-- ── RLS: tables / rows / table_views — read to view, write to mutate ────

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['tables', 'rows', 'table_views'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I_workspace_member ON public.%I', t, t);

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_read ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_read ON public.%I
             FOR SELECT
             USING (
                 public.check_workspace_permission(
                     workspace_id,
                     (nullif(current_setting(''app.current_user_id'', TRUE), ''''))::UUID,
                     ''read''
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_insert ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_insert ON public.%I
             FOR INSERT
             WITH CHECK (
                 public.check_workspace_permission(
                     workspace_id,
                     (nullif(current_setting(''app.current_user_id'', TRUE), ''''))::UUID,
                     ''write''
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_update ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_update ON public.%I
             FOR UPDATE
             USING (
                 public.check_workspace_permission(
                     workspace_id,
                     (nullif(current_setting(''app.current_user_id'', TRUE), ''''))::UUID,
                     ''write''
                 )
             )
             WITH CHECK (
                 public.check_workspace_permission(
                     workspace_id,
                     (nullif(current_setting(''app.current_user_id'', TRUE), ''''))::UUID,
                     ''write''
                 )
             )', t, t
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS %I_write_delete ON public.%I', t, t
        );
        EXECUTE format(
            'CREATE POLICY %I_write_delete ON public.%I
             FOR DELETE
             USING (
                 public.check_workspace_permission(
                     workspace_id,
                     (nullif(current_setting(''app.current_user_id'', TRUE), ''''))::UUID,
                     ''write''
                 )
             )', t, t
        );
    END LOOP;
END $$;

-- All dependent policies now redefined against check_workspace_permission.
DROP FUNCTION IF EXISTS public.check_workspace_member(UUID, UUID);

-- ── create_workspace: creator gets read + write + owner ──────────────────

CREATE OR REPLACE FUNCTION public.create_workspace(
    p_workspace_name VARCHAR,
    p_by UUID
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_workspace_id UUID;
    v_now          TIMESTAMP;
BEGIN
    INSERT INTO public.workspaces (workspace_name)
    VALUES (p_workspace_name)
    RETURNING workspace_id, created_at INTO v_workspace_id, v_now;

    INSERT INTO public.workspace_members (workspace_id, user_id, action)
    VALUES (v_workspace_id, p_by, 'read'),
           (v_workspace_id, p_by, 'write'),
           (v_workspace_id, p_by, 'owner');

    RETURN jsonb_build_object(
        'workspace_id',   v_workspace_id,
        'workspace_name', p_workspace_name,
        'created_at',     v_now,
        'updated_at',     v_now
    );
END;
$$;

-- ── grant_workspace_action: atomic multi-row grant/revoke ────────────────
-- Deliberately NOT SECURITY DEFINER: it must run as the invoker (the
-- app session, with app.current_user_id already set) so its own
-- INSERT/DELETE statements against workspace_members are subject to
-- the workspace_members_owner RLS policy exactly like a direct query
-- would be — only an existing owner can call this successfully.
-- p_level is the target ceiling: 'read' leaves only a read row, 'write'
-- leaves read+write, 'owner' leaves read+write+owner.

CREATE OR REPLACE FUNCTION public.grant_workspace_action(
    p_workspace_id UUID,
    p_user_id      UUID,
    p_level        VARCHAR
) RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_level NOT IN ('read', 'write', 'owner') THEN
        RAISE EXCEPTION 'Invalid level: %', p_level;
    END IF;

    INSERT INTO public.workspace_members (workspace_id, user_id, action)
    VALUES (p_workspace_id, p_user_id, 'read')
    ON CONFLICT (workspace_id, user_id, action) DO NOTHING;

    IF p_level IN ('write', 'owner') THEN
        INSERT INTO public.workspace_members (workspace_id, user_id, action)
        VALUES (p_workspace_id, p_user_id, 'write')
        ON CONFLICT (workspace_id, user_id, action) DO NOTHING;
    ELSE
        DELETE FROM public.workspace_members
        WHERE  workspace_id = p_workspace_id
        AND    user_id      = p_user_id
        AND    action        = 'write';
    END IF;

    IF p_level = 'owner' THEN
        INSERT INTO public.workspace_members (workspace_id, user_id, action)
        VALUES (p_workspace_id, p_user_id, 'owner')
        ON CONFLICT (workspace_id, user_id, action) DO NOTHING;
    ELSE
        DELETE FROM public.workspace_members
        WHERE  workspace_id = p_workspace_id
        AND    user_id      = p_user_id
        AND    action        = 'owner';
    END IF;
END;
$$;

REVOKE ALL    ON FUNCTION public.grant_workspace_action(UUID, UUID, VARCHAR) FROM public;
GRANT EXECUTE ON FUNCTION public.grant_workspace_action(UUID, UUID, VARCHAR) TO app, mgr;
