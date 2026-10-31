-- LatticeQL compiles string equality into row_data @> JSONB containment.
-- Column expression indexes cannot serve that whole-document predicate.
CREATE INDEX IF NOT EXISTS idx_rows_row_data_gin
    ON public.rows USING gin (row_data);
