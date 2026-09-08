-- upgrade
-- Take check_workspace_permission away from end-user sessions.
--
-- Authorisation is RLS's job (llm.arch.db.md: "PostgreSQL RLS is the
-- authorization boundary"). A backend that can ask the permission
-- question directly is a second enforcement point, and the weaker one:
-- V33's header records the same class of mistake, where the old `role`
-- column gated application code that RLS never read, so every member
-- had full write access regardless of role.
--
-- After the V52 policies and the repository/workspace.py rewrite, the
-- only remaining callers are public.create_row_data_index and
-- public.drop_row_data_index (V47, and V49's replacement). Both are
-- SECURITY DEFINER functions performing DDL that RLS cannot govern, and
-- both execute as the function owner -- so `app` needs no EXECUTE of
-- its own. `mgr` keeps it: that role is BYPASSRLS by design (V1) and
-- backs admin tooling, which has no policy to lean on.
--
-- Ordering: this must be applied together with the backend change that
-- drops the five call sites in repository/workspace.py. It is safe to
-- apply first because the release is breaking and runs behind an
-- announced maintenance window -- no old code serves traffic against
-- the new grants. Applying it to a running old backend would 500 every
-- route that reaches list_by_user, get_first_owned_workspace,
-- is_member, is_owner, can_write or get_user_level.

REVOKE EXECUTE ON
    FUNCTION public.check_workspace_permission(UUID, UUID, VARCHAR) FROM app;
