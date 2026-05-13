-- upgrade
-- V42: Recreate _build_template_columns() with hex colors instead of Tailwind
-- class strings, so future PM/CRM tables get vivid semantic colors that the
-- new color picker (vanilla-colorful) renders directly.
--
-- Existing tables are untouched — their Tailwind class colors still render
-- via the FE legacy lookup. Users who want hex colors on old tables can
-- pick a new one in the ManageOptions modal.
--
-- V38 still owns the function signature; this migration just replaces the
-- body via CREATE OR REPLACE.

CREATE OR REPLACE FUNCTION _BUILD_TEMPLATE_COLUMNS(p_kind TEXT)
RETURNS JSONB
LANGUAGE plpgsql
IMMUTABLE
SET search_path = public, pg_temp
AS $$
DECLARE
    v_specs JSONB;
    v_result JSONB := '[]'::JSONB;
    v_spec JSONB;
    v_pos INT := 0;
BEGIN
    IF p_kind = 'blank' THEN
        v_specs := '[
            {"name":"Title","type":"text","options":{}},
            {"name":"Doc","type":"doc","options":{}},
            {"name":"Description","type":"text","options":{}}
        ]'::JSONB;
    ELSIF p_kind = 'pm' THEN
        v_specs := '[
            {"name":"Title","type":"text","options":{}},
            {"name":"Doc","type":"doc","options":{}},
            {"name":"Type","type":"select","options":{"choices":[
                {"value":"epic","color":"#9b6cd6"},
                {"value":"story","color":"#4a90e2"},
                {"value":"task","color":"#5cc28f"},
                {"value":"bug","color":"#e06060"}
            ]}},
            {"name":"Status","type":"select","options":{"choices":[
                {"value":"todo","color":"#a0a0a0"},
                {"value":"in_progress","color":"#4a90e2"},
                {"value":"testing","color":"#d4c050"},
                {"value":"debugging","color":"#e06060"},
                {"value":"review","color":"#e89050"},
                {"value":"done","color":"#5cc28f"},
                {"value":"merged","color":"#4ec8b0"}
            ]}},
            {"name":"Priority","type":"select","options":{"choices":[
                {"value":"critical","color":"#e06060"},
                {"value":"high","color":"#e89050"},
                {"value":"medium","color":"#d4c050"},
                {"value":"low","color":"#a0a0a0"}
            ]}},
            {"name":"Assignee","type":"text","options":{}},
            {"name":"Start Date","type":"date","options":{}},
            {"name":"Due Date","type":"date","options":{}},
            {"name":"Estimate","type":"number","options":{}},
            {"name":"Tags","type":"tags","options":{}},
            {"name":"Description","type":"text","options":{}},
            {"name":"Parent","type":"text","options":{}}
        ]'::JSONB;
    ELSIF p_kind = 'crm' THEN
        v_specs := '[
            {"name":"Title","type":"text","options":{}},
            {"name":"Doc","type":"doc","options":{}},
            {"name":"Stage","type":"select","options":{"choices":[
                {"value":"lead","color":"#a0a0a0"},
                {"value":"qualified","color":"#4a90e2"},
                {"value":"proposal","color":"#d4c050"},
                {"value":"won","color":"#5cc28f"},
                {"value":"lost","color":"#e06060"}
            ]}},
            {"name":"Value","type":"number","options":{}},
            {"name":"Owner","type":"text","options":{}},
            {"name":"Close Date","type":"date","options":{}},
            {"name":"Tags","type":"tags","options":{}},
            {"name":"Description","type":"text","options":{}}
        ]'::JSONB;
    ELSE
        RAISE EXCEPTION 'Unknown template kind: %', p_kind;
    END IF;

    FOR v_spec IN SELECT * FROM JSONB_ARRAY_ELEMENTS(v_specs)
    LOOP
        v_result := v_result || JSONB_BUILD_ARRAY(
            JSONB_BUILD_OBJECT(
                'column_id', GEN_RANDOM_UUID()::TEXT,
                'name', v_spec->>'name',
                'type', v_spec->>'type',
                'options', COALESCE(v_spec->'options', '{}'::JSONB),
                'position', v_pos,
                'created_at', NOW()::TEXT
            )
        );
        v_pos := v_pos + 1;
    END LOOP;
    RETURN v_result;
END;
$$;
