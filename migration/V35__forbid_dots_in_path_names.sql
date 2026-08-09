-- V35 — forbid dots in names that become URL/S3 path segments
--
-- workspace_id remains the UUID identity and the first MinIO key segment.
-- workspace_name is the browser-path alias; table_id is both a browser-path
-- segment and the second MinIO key segment. A dot can make infrastructure
-- treat either path as a file, so normalize existing values and reject dots
-- at the database boundary for every future write path.

UPDATE public.workspaces
SET workspace_name = replace(workspace_name, '.', '-')
WHERE position('.' IN workspace_name) > 0;

UPDATE public.tables
SET table_id = replace(table_id, '.', '-')
WHERE position('.' IN table_id) > 0;

ALTER TABLE public.workspaces
DROP CONSTRAINT IF EXISTS workspaces_workspace_name_no_dot;

ALTER TABLE public.workspaces
ADD CONSTRAINT workspaces_workspace_name_no_dot
CHECK (position('.' IN workspace_name) = 0);

ALTER TABLE public.tables
DROP CONSTRAINT IF EXISTS tables_table_id_no_dot;

ALTER TABLE public.tables
ADD CONSTRAINT tables_table_id_no_dot
CHECK (position('.' IN table_id) = 0);
