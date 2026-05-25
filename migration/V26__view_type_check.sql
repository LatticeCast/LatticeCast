-- V26: Enforce allowed view types at the PG level via CHECK
-- constraint on config->>'type'. Previously validated in
-- Python (USER_VIEW_TYPES tuple) — now the DB is the SSOT.

ALTER TABLE public.table_views
    ADD CONSTRAINT table_views_valid_type CHECK (
        config ->> 'type' IN (
            'table',
            'kanban',
            'timeline',
            'dashboard',
            'workflow'
        )
    );
