-- The V11 index-helper overloads have no workspace permission check.  V49
-- retired them, but repeat the DROP at the current compatibility boundary so
-- every upgraded database converges even if an operator restored an old dump.
-- The only supported signatures are the workspace-scoped V57 functions.

DROP FUNCTION IF EXISTS public.create_row_data_index(TEXT, TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.drop_row_data_index(TEXT);
