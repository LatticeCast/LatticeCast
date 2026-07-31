-- upgrade
-- Replace Valkey/Redis (schema cache + JWKS cache) with a PostgreSQL
-- UNLOGGED TABLE. UNLOGGED tables skip WAL — fast writes, no
-- replication — and are truncated on crash/unclean shutdown, which is
-- exactly the durability profile a cache needs: losing the contents on
-- crash is fine, both call sites already rebuild on a miss.
--
-- Table lives in `private` (internal system data, no direct app
-- access — see V1). app_user reaches it only through the three
-- SECURITY DEFINER functions below, never the table directly.

CREATE UNLOGGED TABLE IF NOT EXISTS private.cache (
    cache_key  VARCHAR     NOT NULL,
    cache_val  JSONB       NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (cache_key)
);

CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON private.cache (expires_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON private.cache TO dba;
GRANT USAGE ON SCHEMA private TO app;

-- ── cache_get: NULL on miss or expiry ───────────────────────────────────────

CREATE OR REPLACE FUNCTION private.cache_get(
    p_key VARCHAR
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = private, pg_temp
AS $$
DECLARE
    v_val JSONB;
BEGIN
    SELECT cache_val INTO v_val
    FROM   private.cache
    WHERE  cache_key = p_key
    AND    expires_at > now();

    RETURN v_val;
END;
$$;

REVOKE ALL ON FUNCTION private.cache_get(VARCHAR) FROM public;
GRANT EXECUTE ON FUNCTION private.cache_get(VARCHAR) TO app, mgr;

-- ── cache_set: upsert with TTL ───────────────────────────────────────────────

CREATE OR REPLACE FUNCTION private.cache_set(
    p_key         VARCHAR,
    p_val         JSONB,
    p_ttl_seconds INT
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = private, pg_temp
AS $$
BEGIN
    INSERT INTO private.cache (cache_key, cache_val, expires_at)
    VALUES (p_key, p_val, now() + make_interval(secs => p_ttl_seconds))
    ON CONFLICT (cache_key) DO UPDATE
        SET cache_val  = EXCLUDED.cache_val,
            expires_at = EXCLUDED.expires_at;
END;
$$;

REVOKE ALL    ON
    FUNCTION private.cache_set(VARCHAR, JSONB, INT) FROM public;
GRANT EXECUTE ON
    FUNCTION private.cache_set(VARCHAR, JSONB, INT) TO app, mgr;

-- ── cache_delete ──────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION private.cache_delete(
    p_key VARCHAR
) RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = private, pg_temp
AS $$
BEGIN
    DELETE FROM private.cache WHERE cache_key = p_key;
END;
$$;

REVOKE ALL ON FUNCTION private.cache_delete(VARCHAR) FROM public;
GRANT EXECUTE ON FUNCTION private.cache_delete(VARCHAR) TO app, mgr;
