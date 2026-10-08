-- upgrade
-- Immutable objects are registered before upload. A durable queue recovers
-- interrupted uploads and retires old objects only after metadata commits.
CREATE TABLE IF NOT EXISTS private.blob_objects (
    object_key   TEXT    PRIMARY KEY,
    workspace_id UUID    NOT NULL,
    table_id     VARCHAR NOT NULL,
    row_id       BIGINT  NOT NULL,
    column_id    TEXT    NOT NULL,
    FOREIGN KEY (workspace_id, table_id, row_id)
        REFERENCES public.rows (workspace_id, table_id, row_id)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS private.blob_cleanup_queue (
    object_key TEXT        PRIMARY KEY,
    queued_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

GRANT SELECT, DELETE ON private.blob_objects TO mgr;
GRANT SELECT, DELETE ON private.blob_cleanup_queue TO mgr;

-- Trust only existing descriptors whose key matches their original cell.
INSERT INTO private.blob_objects
    (object_key, workspace_id, table_id, row_id, column_id)
SELECT
    cell.value ->> 'key' AS object_key,
    r.workspace_id,
    r.table_id,
    r.row_id,
    cell.key AS column_id
FROM public.rows AS r
CROSS JOIN LATERAL JSONB_EACH(r.row_data) AS cell
WHERE cell.value ->> 'key' = CONCAT(
    r.workspace_id, '/', r.table_id, '/rows/', r.row_id, '/blobs/', cell.key
)
ON CONFLICT (object_key) DO NOTHING;

CREATE OR REPLACE FUNCTION public.register_blob_object(
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_row_id       BIGINT,
    p_column_id    TEXT,
    p_object_key   TEXT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_base TEXT;
BEGIN
    IF p_workspace_id NOT IN (
        SELECT public.current_user_workspaces('write')
    ) THEN
        RAISE EXCEPTION 'workspace write permission required'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.rows AS r
        JOIN public.tables AS t USING (workspace_id, table_id)
        CROSS JOIN LATERAL jsonb_array_elements(t.config -> 'columns') AS c
        WHERE r.workspace_id = p_workspace_id AND r.table_id = p_table_id
          AND r.row_id = p_row_id AND c ->> 'column_id' = p_column_id
          AND c ->> 'type' = 'blob'
    ) THEN
        RAISE EXCEPTION 'blob cell not found'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    v_base := concat(p_workspace_id, '/', p_table_id, '/rows/',
                     p_row_id, '/blobs/', p_column_id, '/');
    IF left(p_object_key, length(v_base)) IS DISTINCT FROM v_base
       OR substring(p_object_key FROM length(v_base) + 1)
          !~ '^([.]pending/)?[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'invalid blob object key'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    INSERT INTO private.blob_objects
        (object_key, workspace_id, table_id, row_id, column_id)
    VALUES (p_object_key, p_workspace_id, p_table_id, p_row_id, p_column_id);
    INSERT INTO private.blob_cleanup_queue (object_key) VALUES (p_object_key);
END;
$$;

CREATE OR REPLACE FUNCTION public.blob_object_belongs_to_cell(
    p_object_key   TEXT,
    p_workspace_id UUID,
    p_table_id     VARCHAR,
    p_row_id       BIGINT,
    p_column_id    TEXT
) RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = public, pg_temp
AS $$
    SELECT p_workspace_id IN (
        SELECT public.current_user_workspaces('read')
    ) AND EXISTS (
        SELECT 1 FROM private.blob_objects
        WHERE object_key = p_object_key AND workspace_id = p_workspace_id
          AND table_id = p_table_id AND row_id = p_row_id
          AND column_id = p_column_id
    );
$$;

CREATE OR REPLACE FUNCTION private.queue_retired_blob_objects()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_data JSONB;
BEGIN
    v_data := CASE WHEN TG_OP = 'DELETE' THEN '{}'::JSONB ELSE NEW.row_data END;
    INSERT INTO private.blob_cleanup_queue (object_key)
    SELECT obj.object_key
    FROM private.blob_objects AS obj
    JOIN LATERAL jsonb_each(OLD.row_data) AS cell
      ON cell.value ->> 'key' = obj.object_key
    WHERE obj.workspace_id = OLD.workspace_id AND obj.table_id = OLD.table_id
      AND obj.row_id = OLD.row_id AND obj.column_id = cell.key
      AND (v_data -> cell.key ->> 'key') IS DISTINCT FROM obj.object_key
    ON CONFLICT (object_key) DO NOTHING;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

DROP TRIGGER IF EXISTS trg_rows_retire_blobs ON public.rows;
CREATE TRIGGER trg_rows_retire_blobs
BEFORE UPDATE OF row_data OR DELETE ON public.rows
FOR EACH ROW EXECUTE FUNCTION private.queue_retired_blob_objects();

REVOKE ALL ON FUNCTION
    public.register_blob_object(UUID, VARCHAR, BIGINT, TEXT, TEXT) FROM public;
REVOKE ALL ON FUNCTION
    public.blob_object_belongs_to_cell(TEXT, UUID, VARCHAR, BIGINT, TEXT)
    FROM public;
REVOKE ALL ON FUNCTION private.queue_retired_blob_objects() FROM public;
GRANT EXECUTE ON FUNCTION
    public.register_blob_object(UUID, VARCHAR, BIGINT, TEXT, TEXT) TO app;
GRANT EXECUTE ON FUNCTION
    public.blob_object_belongs_to_cell(TEXT, UUID, VARCHAR, BIGINT, TEXT) TO app;
