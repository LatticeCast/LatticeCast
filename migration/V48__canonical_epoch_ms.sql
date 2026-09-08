-- upgrade
-- Canonical timestamp representation for row_data date/datetime cells.
--
-- One shape for both types: a JSON *number* holding epoch milliseconds
-- in UTC. `datetime` is natural millisecond precision; `date` is the
-- same number landing on UTC midnight, so its low-order digits are
-- zeros. The column type decides only how a client renders and edits
-- the value -- it is never encoded in the value itself.
--
-- Why epoch integers and not an ISO string: a row_data index
-- expression must be IMMUTABLE. `(row_data ->> col)::BIGINT` is, and
-- the number branch at V47:70 already proves an I/O cast works in that
-- position. Every text->timestamp cast is only STABLE, which is why
-- V18 had to wrap one in a function *declared* IMMUTABLE -- a promise
-- PostgreSQL cannot verify. Epoch integers remove the need to make it.
--
-- These helpers are STABLE, not IMMUTABLE: they are called only on the
-- write path (V49), never inside an index, so they have no reason to
-- overstate their volatility.

-- ── Legacy string parsing ───────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public._parse_legacy_ts_ms(
    p_text TEXT
) RETURNS BIGINT
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_iso TEXT;
    v_ts  TIMESTAMPTZ;
BEGIN
    -- Digit-only strings are genuinely ambiguous: 20250908 is both a
    -- plausible YYYYMMDD and a plausible epoch-ms. Resolve it exactly
    -- the way the frontend's formatDate() already did
    -- (table.utils.ts:228-236), so the V49 backfill reproduces what
    -- users have actually been seeing on screen:
    --     6 digits  -> YYMMDD, 20xx century (formatDate hardcoded '20')
    --     8 digits  -> YYYYMMDD
    --    14 digits  -> YYYYMMDDHH24MISS
    --    any other  -> already epoch milliseconds
    -- This heuristic applies only to legacy *string* cells. Once V49
    -- normalizes a cell it is a JSON number and is never re-parsed, so
    -- the ambiguity is retired with the migration rather than kept.
    IF p_text ~ '^[0-9]{6}$' THEN
        v_iso := '20' || substr(p_text, 1, 2)
              || '-' || substr(p_text, 3, 2)
              || '-' || substr(p_text, 5, 2);
    ELSIF p_text ~ '^[0-9]{8}$' THEN
        v_iso := substr(p_text, 1, 4)
              || '-' || substr(p_text, 5, 2)
              || '-' || substr(p_text, 7, 2);
    ELSIF p_text ~ '^[0-9]{14}$' THEN
        v_iso := substr(p_text, 1, 4)
              || '-' || substr(p_text, 5, 2)
              || '-' || substr(p_text, 7, 2)
              || ' ' || substr(p_text, 9, 2)
              || ':' || substr(p_text, 11, 2)
              || ':' || substr(p_text, 13, 2);
    ELSIF p_text ~ '^-?[0-9]+$' THEN
        RETURN p_text::BIGINT;
    ELSE
        v_iso := p_text;
    END IF;

    -- Honour an explicit offset; read a naive value as UTC rather than
    -- the session zone, so the result never depends on who runs the
    -- statement. Digit forms above are rewritten to naive ISO, so they
    -- land in the second branch by construction.
    BEGIN
        IF v_iso ~ '(Z|z|[+-][0-9]{2}:?[0-9]{2})$' THEN
            v_ts := v_iso::TIMESTAMPTZ;
        ELSE
            v_ts := (v_iso::TIMESTAMP) AT TIME ZONE 'UTC';
        END IF;
    EXCEPTION
        WHEN others THEN
            RAISE EXCEPTION 'unparseable timestamp value: %', p_text
                USING ERRCODE = 'invalid_parameter_value';
    END;

    RETURN floor(extract(EPOCH FROM v_ts) * 1000)::BIGINT;
END;
$$;

-- ── Canonicalisation ────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION public.to_canonical_epoch_ms(
    p_value JSONB,
    p_type  TEXT
) RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_text TEXT;
    v_ms   BIGINT;
BEGIN
    IF p_type NOT IN ('date', 'datetime') THEN
        RAISE EXCEPTION 'not a timestamp column type: %', p_type
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- Absent or explicitly cleared cell is NULL, never 0: zero is a
    -- valid instant (1970-01-01T00:00:00Z) and must not double as
    -- "empty".
    IF p_value IS NULL OR jsonb_typeof(p_value) = 'null' THEN
        RETURN 'null'::JSONB;
    END IF;

    IF jsonb_typeof(p_value) = 'number' THEN
        v_ms := trunc((p_value #>> '{}')::NUMERIC)::BIGINT;
    ELSIF jsonb_typeof(p_value) = 'string' THEN
        v_text := btrim(p_value #>> '{}');
        IF v_text = '' THEN
            RETURN 'null'::JSONB;
        END IF;
        v_ms := public._parse_legacy_ts_ms(v_text);
    ELSE
        RAISE EXCEPTION
            'timestamp cell must be number, string or null; got %',
            jsonb_typeof(p_value)
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    -- `date` is midnight-aligned in UTC. floor(), not trunc(), so a
    -- pre-1970 (negative) value floors to the earlier midnight and the
    -- calendar day a client sent is the calendar day stored.
    IF p_type = 'date' THEN
        v_ms := (floor(v_ms::NUMERIC / 86400000) * 86400000)::BIGINT;
    END IF;

    RETURN to_jsonb(v_ms);
END;
$$;

-- ── Grants ──────────────────────────────────────────────────────────────

REVOKE ALL    ON
    FUNCTION public._parse_legacy_ts_ms(TEXT) FROM public;
GRANT EXECUTE ON
    FUNCTION public._parse_legacy_ts_ms(TEXT) TO app, mgr;

REVOKE ALL    ON
    FUNCTION public.to_canonical_epoch_ms(JSONB, TEXT) FROM public;
GRANT EXECUTE ON
    FUNCTION public.to_canonical_epoch_ms(JSONB, TEXT) TO app, mgr;
