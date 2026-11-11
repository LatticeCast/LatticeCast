-- upgrade
-- public.rows has thousands of table-scoped indexes. Even a primary-key
-- SELECT on rows takes relation locks on those indexes, so blob cleanup must
-- decide eligibility from this small private ownership table instead.
-- Existing ownership rows remain NULL (unknown) and are retained safely;
-- newly registered objects start unreferenced until the row trigger publishes
-- their key in the same transaction.
ALTER TABLE private.blob_objects ADD COLUMN is_referenced BOOLEAN;
ALTER TABLE private.blob_objects ALTER COLUMN is_referenced SET DEFAULT FALSE;

CREATE OR REPLACE FUNCTION private.queue_retired_blob_objects()
 RETURNS TRIGGER
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public', 'pg_temp'
AS $function$
DECLARE
    v_data JSONB;
BEGIN
    v_data := CASE WHEN TG_OP = 'DELETE' THEN '{}'::JSONB ELSE NEW.row_data END;

    IF TG_OP = 'UPDATE' THEN
        UPDATE private.blob_objects AS owned
        SET is_referenced = TRUE
        FROM jsonb_each(NEW.row_data) AS cell
        WHERE owned.object_key = cell.value ->> 'key'
          AND owned.table_id = NEW.table_id
          AND owned.row_id = NEW.row_id
          AND owned.column_id = cell.key
          AND owned.is_referenced IS DISTINCT FROM TRUE;
    END IF;

    UPDATE private.blob_objects AS owned
    SET is_referenced = FALSE
    FROM jsonb_each(OLD.row_data) AS cell
    WHERE owned.object_key = cell.value ->> 'key'
      AND owned.table_id = OLD.table_id
      AND owned.row_id = OLD.row_id
      AND owned.column_id = cell.key
      AND (v_data -> cell.key ->> 'key') IS DISTINCT FROM owned.object_key;

    INSERT INTO private.blob_cleanup_queue (object_key)
    SELECT owned.object_key
    FROM private.blob_objects AS owned
    JOIN LATERAL jsonb_each(OLD.row_data) AS cell
      ON cell.value ->> 'key' = owned.object_key
    WHERE owned.table_id = OLD.table_id
      AND owned.row_id = OLD.row_id
      AND owned.column_id = cell.key
      AND (v_data -> cell.key ->> 'key') IS DISTINCT FROM owned.object_key
    ON CONFLICT (object_key) DO NOTHING;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$function$;
