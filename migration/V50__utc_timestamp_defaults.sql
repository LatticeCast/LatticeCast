-- upgrade
-- Every stored timestamp is UTC+0. Nothing in the database knows about
-- timezones; localisation is a frontend/user-config concern.
--
-- The column type therefore stays TIMESTAMP. No ALTER COLUMN TYPE, no
-- table rewrite, no ACCESS EXCLUSIVE lock, and no reinterpretation of
-- existing rows -- they are already naive UTC, which under this
-- convention is already correct. Python's datetime.utcnow() defaults
-- (models/row.py, table.py, user.py, workspace.py, table_view.py) are
-- likewise already correct and need no change, and V46's
-- `v_now TIMESTAMP` stays as it is.
--
-- One thing does have to change, and it is not a timezone feature: it
-- is what makes the stored value deterministic. `DEFAULT now()` returns
-- timestamptz, and storing that into TIMESTAMP silently rebases it to
-- the session TimeZone and drops the offset. core/db.py's _make_engine
-- pins only search_path, so today the wall clock PostgreSQL records
-- depends on ambient configuration. Two fixes, belt and braces:
--
--   1. Pin the database's timezone, so every connection and every role
--      agrees regardless of what a client sends.
--   2. Make each default explicitly UTC, so the column definition says
--      what it stores and holds even if a session overrides the GUC.
--
-- private.schema_migrations.applied_at is left alone: it is the
-- migration runner's own bookkeeping and altering the table the runner
-- is appending to during its own run invites an unrelated failure.

-- ── 1. Database-wide timezone ───────────────────────────────────────────
-- Applies to new connections. Set on the database rather than per role:
-- ALTER ROLE only takes effect for a login role that is the session
-- role, so a setting on the NOLOGIN group roles (app / mgr / dba) would
-- silently do nothing.

DO $$
BEGIN
    EXECUTE format(
        'ALTER DATABASE %I SET timezone = ''UTC''',
        current_database()
    );
END;
$$;

-- ── 2. Explicit UTC defaults ────────────────────────────────────────────
-- now() AT TIME ZONE 'UTC' yields a TIMESTAMP holding the instant
-- rendered in UTC, independent of any session setting.

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT *
        FROM (VALUES
            ('public', 'rows',          'created_at'),
            ('public', 'rows',          'updated_at'),
            ('public', 'tables',        'created_at'),
            ('public', 'tables',        'updated_at'),
            ('public', 'workspaces',    'created_at'),
            ('public', 'workspaces',    'updated_at'),
            ('public', 'table_views',   'created_at'),
            ('public', 'table_views',   'updated_at'),
            ('auth',   'users',         'created_at'),
            ('auth',   'users',         'updated_at'),
            ('gdpr',   'user_password', 'updated_at')
        ) AS target (schema_name, table_name, column_name)
    LOOP
        IF EXISTS (
            SELECT 1
            FROM   information_schema.columns AS c
            WHERE  c.table_schema = r.schema_name
            AND    c.table_name   = r.table_name
            AND    c.column_name  = r.column_name
        ) THEN
            EXECUTE format(
                'ALTER TABLE %I.%I ALTER COLUMN %I '
                'SET DEFAULT (now() AT TIME ZONE ''UTC'')',
                r.schema_name, r.table_name, r.column_name
            );
        END IF;
    END LOOP;
END;
$$;
