-- upgrade
-- Stop flooring `date` cells to UTC midnight.
--
-- V48 aligned a `date` value to the start of its UTC day. That looked tidy
-- and it was wrong: it makes the frontend timezone conversion this design
-- asks for impossible. A viewer at UTC-5 who picks 2026-12-31 sends the
-- instant 2026-12-31T05:00:00Z; flooring rewrites it to
-- 2026-12-31T00:00:00Z, and converting that back to their zone renders
-- 2026-12-30. The day the user typed cannot survive a round trip.
--
-- `date` and `datetime` are one storage shape: an epoch-millisecond integer
-- in UTC, with no alignment rule. The column type says which input widget a
-- client offers and nothing more; it is not a claim about the value. That is
-- what makes "store UTC, convert in the frontend" hold for both of them.
--
-- Existing values are left alone. Anything already floored is still a valid
-- instant, and re-deriving an intent that was discarded is not possible --
-- the offset it was floored from is gone. New writes keep their time.

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

    -- Absent or explicitly cleared cell is NULL, never 0: zero is a valid
    -- instant (1970-01-01T00:00:00Z) and must not double as "empty".
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

    -- No alignment: `date` keeps the instant it was given, exactly like
    -- `datetime`. A bare calendar string still lands on that day's UTC
    -- midnight because _parse_legacy_ts_ms reads a zone-less value as UTC,
    -- which is the right default for a value that carries no offset.
    RETURN to_jsonb(v_ms);
END;
$$;

REVOKE ALL    ON
    FUNCTION public.to_canonical_epoch_ms(JSONB, TEXT) FROM public;
GRANT EXECUTE ON
    FUNCTION public.to_canonical_epoch_ms(JSONB, TEXT) TO app, mgr;
