-- Two name rules that only the API enforced now live in the database, so a
-- direct write is refused too and the API only relays the refusal.
--
-- NOT VALID: new and updated rows are checked, existing rows are not scanned,
-- so a database that already holds a violating name still migrates.

-- A workspace name is the first URL segment, so it must not shadow a route.
ALTER TABLE public.workspaces
DROP CONSTRAINT IF EXISTS workspaces_workspace_name_not_reserved;

ALTER TABLE public.workspaces
ADD CONSTRAINT workspaces_workspace_name_not_reserved CHECK (
    lower(workspace_name) NOT IN (
        'settings', 'config', 'members', 'login', 'callback', 'debug', 'api'
    )
) NOT VALID;

ALTER TABLE public.table_views
DROP CONSTRAINT IF EXISTS table_views_name_not_blank;

ALTER TABLE public.table_views
ADD CONSTRAINT table_views_name_not_blank CHECK (
    btrim(coalesce(config ->> 'name', '')) <> ''
) NOT VALID;
