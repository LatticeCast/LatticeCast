-- Passwordless login is an explicit opt-in, not the absence of a row.
--
-- gdpr.user_password.allow_no_pwd: only TRUE lets the account log in without
-- a password. NULL (the default) and FALSE do not. password_login treats:
--   password_hash set          -> the password must match
--   no hash, allow_no_pwd TRUE -> login without a password
--   anything else (including no row at all) -> login is refused
--
-- A hash and allow_no_pwd = TRUE together would be ambiguous (does the
-- password still count?), so the CHECK forbids it. password_hash becomes
-- nullable so an opted-in account can carry no hash.
--
-- No backfill: accounts that have no row today stop logging in until an
-- admin opts them in (POST/PUT /admin/users allow_no_pwd) or they set a
-- password.

ALTER TABLE gdpr.user_password
    ALTER COLUMN password_hash DROP NOT NULL;

ALTER TABLE gdpr.user_password
    ADD COLUMN IF NOT EXISTS allow_no_pwd BOOLEAN;

ALTER TABLE gdpr.user_password
    DROP CONSTRAINT IF EXISTS user_password_login_mode;
ALTER TABLE gdpr.user_password
    ADD CONSTRAINT user_password_login_mode
    CHECK (allow_no_pwd IS NOT TRUE OR password_hash IS NULL);

-- Setting a password ends passwordless mode: the flag goes back to NULL so a
-- later password removal can never silently re-open the account.
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

    INSERT INTO gdpr.user_password (user_id, password_hash, allow_no_pwd)
    VALUES (v_user_id, p_password_hash, NULL)
    ON CONFLICT (user_id) DO UPDATE
    SET    password_hash = EXCLUDED.password_hash,
           allow_no_pwd  = NULL,
           updated_at    = now();
END;
$$;
