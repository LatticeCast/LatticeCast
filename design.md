# LatticeCast — table identity: one global integer `table_id`

Status: proposal v2 (replaces the workspace-in-path design, kept as Appendix B)
Scope: `public.tables` identity, every surface that carries a `table_id`, and the API
contract around it. Row identity is unchanged.

## TL;DR (中文)

`table_id` 目前是「workspace 內的 slug」，既是主鍵也是顯示名，所以同一個 slug 出現在兩個
workspace 時就註定有歧義。這次把 `table_id` 改成 **全域單調遞增整數（identity）**，
`table_name` 另外存、每個 workspace 內唯一。因為 id 全域唯一，現有的
`/tables/{table_id}/...` 路徑形狀完全不用改，`GET /tables/{id}?workspace_id=` 也不用再
有那個 query 參數。`rows` 主鍵維持 `(workspace_id, table_id, row_id)`。

落地分兩階段，公開 API 在兩階段之間**不變**：
  Phase 1：加 `table_name` + `table_seq BIGINT IDENTITY`，API 立刻改成吃/吐整數 id
           （內部仍用 slug 查資料列），外部 consumer 一次改完。
  Phase 2：把 `rows` / `table_views` / `blob_objects` 的 `table_id` 換成 BIGINT、
           索引改名、LQL 以 name 建 schema，最後 drop slug 欄位。API 不動。

最大的代價只有一個：`public.rows` 的一次全表改寫（§6.2）。

---

## 1. Problem

Composite PK (`migration/V6__tables.sql:6-11`, `backend/src/models/table.py:41-45`):

```sql
CREATE TABLE public.tables (
    workspace_id UUID    NOT NULL,
    table_id     VARCHAR NOT NULL,      -- human slug: 'job_log', 'announcement', …
    PRIMARY KEY (workspace_id, table_id)
);
```

* `table_id` is simultaneously the identity **and** the display name. There is no third
  column, so "give me the table's uuid" has no answer today — the uuid in the URL is the
  *workspace*.
* Uniqueness is per workspace. Resolution without a workspace scope ends in `.first()`
  (`repository/table.py:62-79`), which is why `job_log` in one workspace silently resolves
  to the other one.
* Only `GET /tables/{id}` accepts `?workspace_id=`; the other 20 table-scoped routes do not,
  so every mutation of a name-colliding table is a coin flip. The workaround in use (delete
  the duplicate → mutate → rebuild as `<uuid>-log` → rename back) is a data-loss window per
  step.

Worse, the slug is mutable: `PUT /tables/{table_id}` renames the PK
(`repository/table.py:86-105`), so today a rename changes the identity of the table, the
address of every row/blob, and the key of the LatticeQL schema (`lattice_ql.py:65`).

## 2. Decision

**`table_id` becomes a globally unique, monotonically increasing bigint (`GENERATED ALWAYS
AS IDENTITY`). Display names move to a new `table_name` column, unique per workspace. Row
identity stays exactly as it is: `PRIMARY KEY (workspace_id, table_id, row_id)`.**

Consequences that make this the chosen design:

1. **Addressing becomes total.** `table_id` alone identifies a table, so `/tables/{id}/…`
   keeps its shape and `?workspace_id=` disappears instead of spreading to 20 more routes.
2. **Identity stops moving.** Rename touches `table_name` only; rows, blob keys, views and
   stored LQL stay valid across a rename.
3. **`workspace_id` stays in `rows` and `table_views`.** It is redundant now (derivable from
   `table_id`) but it is what the RLS policies filter on and what keeps per-workspace index
   locality. Not touching it is also what keeps this migration affordable.

The one real cost: every child table that stores `table_id` as `VARCHAR` has to be converted
to `BIGINT`, and `public.rows` is the largest table in the system. That is one planned
rewrite (§6.2), not an ongoing tax.

## 3. Invariants

1. `tables.table_id` is unique **globally**, immutable, and never reused (identity sequence).
2. `tables.table_name` is the only human-facing name: unique per workspace, case-normalized,
   mutable, and what the sidebar, API responses and frontend URLs display.
3. Row identity is `(workspace_id, table_id, row_id)`; `row_id` stays per-table monotonic
   (`trg_set_row_id_fn`, `migration/V7__rows.sql:23`). View identity is
   `(workspace_id, table_id, view_id)` (`V9__table_views.sql:16`).
4. The API names a table by `table_id` (int) only. `table_name` is a display field and a
   frontend URL token; the API never resolves a name to an id. Name resolution lives in the
   SvelteKit route layer against the sidebar payload.
5. Workspace membership stays the authorization boundary: `workspace_id` in the URL/body is
   a UUID, and RLS — not the resolver — decides what is reachable. A table outside the
   caller's workspaces is 404, indistinguishable from missing.
6. No identifiers are compared case-insensitively or fuzzy-matched server-side.

## 4. API contract deltas

Path shape is unchanged except for the *type* of `{table_id}` and the removal of the
disambiguating query parameter.

| Endpoint | Before | After |
|---|---|---|
| `POST /tables` | `{table_id: "job_log", workspace_id?}` | `{table_name: "Job Log", workspace_id?: <uuid>}` → 201, response carries the new int id |
| `GET /tables` | list across readable workspaces | same, each item now has `table_id: int` + `table_name` |
| `GET /tables/{table_id}` | str, optional `?workspace_id=` | int; **query param removed** (id is global) |
| `PUT /tables/{table_id}` | `{table_id: "new-name"}` (renames PK) | `{table_name: "New Name"}` (renames display only; id unchanged); 409 on per-workspace collision |
| `PATCH /tables/{table_id}` | `{view_order?, default_view?, col_order?}` | unchanged |
| `DELETE /tables/{table_id}` | str | int |
| `POST /tables/template/{kind}` | `{table_id, workspace_id?}` | `{table_name, workspace_id?: <uuid>}` |

`TableResponse`:

```json
{"table_id": 42, "table_name": "Job Log", "workspace_id": "…",
 "columns": [], "view_order": [0], "default_view": 0, "views": [],
 "created_at": "…", "updated_at": "…"}
```

`GET /workspaces_tables` (sidebar bulk payload, today `GET /sidebar`) mirrors it:

```json
{"workspaces": [{"workspace_id": "…", "workspace_name": "pm", "level": "owner"}],
 "tables": [{"workspace_id": "…", "table_id": 42, "table_name": "Job Log",
             "config": {"columns": [], "view_order": [0], "default_view": 0}}]}
```

Everything else (`columns`, `views`, `rows`, blob cells, dashboard block query, storage,
admin) keeps its current shape — its `{table_id}` segment simply becomes numeric.

### 4.1 Compatibility window (one release)

Old clients (tappi, seo-system, ad-hoc curl) send slugs. During the window:

* **Reads** (`GET`) accept a non-numeric segment by resolving it as a legacy name, scoped by
  RLS, and answer with `Deprecation: true` + `Link: </api/v1/tables/<id>>;
  rel="successor-version"`. This keeps the old ambiguity for one release — knowingly, and
  logged.
* **Writes** (`POST`/`PUT`/`PATCH`/`DELETE`) accept **integers only** and return 409 with
  `detail: "table_id must be numeric; read GET /tables to map table_name → table_id"` for a
  slug. No mutation can hit the wrong tenant during the window.
* `table_name` equals the old slug after backfill, so a consumer's migration is: call
  `GET /workspaces_tables` once, match `(workspace_id, table_name)`, store the int.

## 5. Data model

### 5.1 Phase 1 DDL (safe, online-ish, no child-table rewrite)

```sql
-- display name: the current PK value becomes it, so nothing reads differently yet
ALTER TABLE public.tables ADD COLUMN table_name TEXT;
UPDATE public.tables SET table_name = table_id;
ALTER TABLE public.tables ALTER COLUMN table_name SET NOT NULL;
CREATE UNIQUE INDEX tables_workspace_name_uq
    ON public.tables (workspace_id, lower(table_name));

-- global identity, used by the API from day one; internal reads still resolve via the slug
ALTER TABLE public.tables ADD COLUMN table_seq BIGINT GENERATED ALWAYS AS IDENTITY;
ALTER TABLE public.tables ADD CONSTRAINT tables_table_seq_uq UNIQUE (table_seq);
```

`table_seq` is what the API calls `table_id`. Phase 2 renames it, so clients never see the
intermediate name.

### 5.2 Phase 2 DDL (the conversion)

Column types, in dependency order — mapping is `slug → table_seq`:

```sql
-- children get the new column nullable, backfill in workspace-sized batches, then swap
ALTER TABLE public.rows         ADD COLUMN table_id_new BIGINT;
ALTER TABLE public.table_views  ADD COLUMN table_id_new BIGINT;
ALTER TABLE private.blob_objects ADD COLUMN table_id_new BIGINT;

UPDATE public.rows r SET table_id_new = t.table_seq
  FROM public.tables t
 WHERE t.workspace_id = r.workspace_id AND t.table_id = r.table_id
   AND r.workspace_id = :batch_workspace;      -- loop per workspace
-- same shape for table_views and private.blob_objects

-- swap: drop FKs/PKs, drop the slug column, rename the new one, recreate constraints
ALTER TABLE public.rows DROP CONSTRAINT rows_pkey;
ALTER TABLE public.rows DROP CONSTRAINT rows_workspace_id_table_id_fkey;
ALTER TABLE public.rows DROP COLUMN table_id;
ALTER TABLE public.rows RENAME COLUMN table_id_new TO table_id;
ALTER TABLE public.rows ALTER COLUMN table_id SET NOT NULL;
ALTER TABLE public.rows ADD PRIMARY KEY (workspace_id, table_id, row_id);
ALTER TABLE public.rows ADD FOREIGN KEY (workspace_id, table_id)
    REFERENCES public.tables (workspace_id, table_id) ON DELETE CASCADE;

-- tables: retire the slug
ALTER TABLE public.tables DROP COLUMN table_id;
ALTER TABLE public.tables RENAME COLUMN table_seq TO table_id;
ALTER TABLE public.tables ADD PRIMARY KEY (workspace_id, table_id);

VACUUM (ANALYZE) public.rows;
```

Why add-column-and-swap instead of `ALTER COLUMN … TYPE BIGINT USING`: the `USING` form
rewrites `rows` **and** all of its indexes inside one `ACCESS EXCLUSIVE` transaction. The
swap form doubles storage for the duration but lets the backfill run in batches and keeps
the exclusive lock to the final DDL.

`workspace_id` stays in both PKs on purpose (§2.3) — dropping it would mean rewriting every
RLS policy and every per-column index predicate for no functional gain.

## 6. Phase 2 fallout, surface by surface

### 6.1 Per-column indexes on `rows`

Index names embed the table id, in two derivations:

* scoped — `_build_rd_idx_name(workspace_id, table_id::text, column_id)`
  → `idx_rd_<ws12>_<table_id[:12]>_<col[:12]>` (`V47…:5`); the live names look like
  `idx_rd_01da4bb423b9_inlineedit17_0a84ba26f6c4`;
* legacy — `_build_rd_idx_name(table_id::text, column_id)` → `idx_rd_<table_id>_<col[:12]>`,
  still reconstructed by `drop_row_data_index` so it can drop a pre-V47 index
  (`V55__restore_legacy_idx_name_helper.sql:1-40`).

`create_row_data_index` verifies the caller's name against the scoped derivation
(`V47…:42`), and `drop_row_data_index` drops **both** families — so the names must be kept
consistent, not dropped and recreated. After conversion the derivation yields digits instead
of slug characters (and the 12-char slug truncation, which can collide for two long slugs
sharing a prefix, stops mattering). Migration step: rename, don't recreate.

```sql
DO $$
DECLARE i RECORD;
BEGIN
  FOR i IN SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'rows'
              AND indexname LIKE 'idx\_rd\_%'
  LOOP
    -- recompute both derivations with the table's new integer id, then
    --   ALTER INDEX public.<old> RENAME TO <new>   (skip when already equal)
  END LOOP;
END $$;
```

### 6.2 `public.rows` rewrite

Single biggest step. `rows` carries `(workspace_id, table_id, row_id)` plus every per-column
index. Budget: batched backfill (§5.2) + one `ACCESS EXCLUSIVE` swap + `VACUUM (ANALYZE)`.
Everything that reads rows in the meantime keeps working, because the repository always
passes `(workspace_id, table_id)` from the resolved table.

### 6.3 PostgreSQL functions (24 take `table_id`)

Their signatures are `VARCHAR` today and become `BIGINT`; bodies that build SQL with
`p_table_id::TEXT` keep working, the ones that `format(%L)` a slug must quote an integer
instead. Full list, by owner migration file:

* template/seed: `create_table_from_template` (V63), `_seed_blank` (V12), `_seed_pm` (V42),
  `_seed_crm` (V12), `_seed_workflow` (V28)
* columns/views: `add_column`, `delete_column`, `drop_row_data_index`, `update_column`,
  `create_view`, `update_view`, `delete_view`, `update_view_order`, `update_col_order`,
  `update_default_view` (V23/V29/V40/V47/V55)
* rows: `patch_row_data`, `put_row_data`, `update_row_data`, `update_blob_cell`,
  `_validate_row_data_mutation` (V44/V45/V49)
* indexes: `_build_rd_idx_name`, `create_row_data_index` (V47/V55/V57)
* blobs: `register_blob_object`, `blob_object_belongs_to_cell` (V64)
* triggers touching `NEW.table_id` (no signature change, but follow the column type):
  `trg_set_row_id_fn` (V7), `trg_set_view_id_fn` (V9), `trg_create_table_schema_fn`

`get_user_sidebar()` (V46) selects `table_id` into its JSON payload — its projection changes
to `table_id` (int) + `table_name`.

### 6.4 Blob object keys — legacy keys are never rewritten

`_blob_storage_key()` (`backend/src/router/api/rows.py:36`) builds
`{workspace_id}/{table_id}/rows/{row_id}/blobs/{column_id}`. After conversion, new uploads
use the numeric id; existing S3 keys keep the old slug segment.

This is safe because ownership is verified against `private.blob_objects` metadata, not the
key prefix (`V64__blob_object_ownership_and_cleanup.sql:97-104`), and the FK to
`public.rows` is `ON UPDATE CASCADE` (`V64:10-13`). Only `register_blob_object` (new
uploads) validates the prefix, and it derives it from the current id. Do **not** rewrite S3
keys.

### 6.5 LatticeQL

The compiled schema is keyed by the slug (`backend/src/config/lattice_ql.py:65`:
`out[t.table_id] = {...}`), so stored dashboard blocks read like `… from job_log …`.

Keep the readable form: key `_build_schema()` by `table_name` and carry `table_id` alongside;
`compile_lql()` then emits `table_id = <int>` in SQL while users keep writing names. Cache
key stays `lql:schema:{workspace_id}`. A rename therefore breaks stored LQL that mentions the
old name — same breakage as today, but now explicit (open question 3).

### 6.6 API routers and repositories

* `repository/table.py`: `resolve_table_global` gains an int path; `update()` writes
  `table_name` and no longer mutates identity.
* `router/api/tables/crud.py` + `templates.py`: request models take `table_name`; path params
  become `int`; `workspace_id` in bodies is a UUID (never a name).
* `router/api/tables/_shared.py`: `_get_table_for_member` keys on int, keeps RLS-only
  authorization and the 404-for-unreachable rule.
* `rows.py`, `columns.py`, `views.py`, `dashboard.py`, `table_schemas.py`: only the
  `table_id` type and the sidebar projection change; the workspace still comes from the
  resolved table, never from the request.

### 6.7 Frontend

* `lib/backend/{tables,views,dashboard}.ts` — 23 call sites, 3 files: `tableId` becomes
  `number`; `fetchTable()` drops `?workspace_id=`.
* `lib/stores/table_schemas.store.ts` — store keys become ints; `currentTableId` is
  `number | null`; sidebar renders `table_name`; `resolveWorkspaceParam` keeps resolving the
  workspace **name** from the URL, and a new analogous helper maps a `table_name` URL token to
  the int id from the sidebar payload, then redirects to the canonical
  `/[workspace_id]/[table_id]` URL. Names stay in the UI layer only.
* Create flows send `table_name` and navigate with the returned id.

### 6.8 Tests and external consumers

* `e2e` — 304 API call sites across 47 files pass a literal `TABLE_ID` string. They become
  "create, capture `table_id` from the 201, use that int", which the helpers already do in
  some places.
* `backend/tests` — 14 references.
* Outside this repo: `seo-system` (45 files), `tappi` (27 files), `deploy-prod` /
  `deploy-stage` configs. All of them must switch reads to `GET /workspaces_tables` →
  match `(workspace_id, table_name)` → keep the int, before the compatibility window closes.

## 7. Authorization and errors (unchanged, restated)

| Status | When |
|---|---|
| 404 | table id does not exist **or** its workspace is not readable by the caller (indistinguishable, by design); unknown column/view/row/blob |
| 403 | member below the required level |
| 409 | duplicate `table_name` in the workspace; duplicate column/view name; blob changed mid-download; slug write during the compatibility window |
| 422 | non-integer id on a write, missing `table_name`, non-blob column for a blob op, reserved workspace name |
| 400 | LatticeQL compile failure; view is not a dashboard |
| 500 | blob storage failure |

Enumeration: sequential ids are guessable, which is acceptable only because RLS makes an
unreachable table indistinguishable from a missing one (404). No endpoint may return a
table's workspace or name to a non-member.

## 8. Test plan / definition of done

1. Two workspaces each with `table_name = 'job_log'` → different int ids;
   `DELETE /tables/<id_a>` removes only A's table (the regression this doc exists for).
2. `POST /tables` in workspace B, then `GET /tables/<id_b>` as a member of A only → 404.
3. `PUT /tables/<id>` with `{table_name}` changes the display name and **not** the id; the
   table's rows, views and blobs remain addressable by the same id.
4. Duplicate `table_name` in one workspace → 409; the same name in another workspace → 201.
5. Compatibility window: `GET /tables/job_log` (slug) → 200 + `Deprecation` header;
   `DELETE /tables/job_log` → 409.
6. After Phase 2: a dashboard block whose LQL says `from job_log` still compiles and returns
   rows; a blob uploaded before the conversion still downloads; a new upload uses a numeric
   key segment.
7. `row_id` stays monotonic per table across the conversion (`trg_set_row_id_fn`).
8. `make lint`, backend integration tests, and the e2e suite pass.

## 9. Rejected alternatives

* **Workspace in the path** (`/workspaces/{ws}/tables/{tid}`, Appendix B). Fixes addressing but
  keeps the slug as a mutable identity, changes every consumer's URL, and needs 21 routes plus
  3 frontend files plus 304 test call sites to be rewritten for a problem that an immutable id
  solves once.
* **Surrogate `table_ref` beside `table_id`, permanently.** Two ids forever; every consumer
  and every cache has to know which one is authoritative. It is exactly Phase 1 of this plan,
  so it is a transition state, not a destination.
* **UUID `table_id`.** Works, but 16 bytes in every PK/FK/index (including `rows`), no natural
  ordering, and unreadable in logs — with no benefit over a bigint identity here.

## Appendix A — surface inventory

| Surface | Count | Reference |
|---|---|---|
| table-scoped API routes | 21 | `router/api/tables/*`, `rows.py`, `dashboard.py` |
| PG functions taking `table_id` | 24 | §6.3 |
| migration files mentioning `table_id` | 37 | `migration/*.sql` |
| frontend call sites | 23 (3 files) | `lib/backend/{tables,views,dashboard}.ts` |
| e2e API call sites | 304 (47 files) | `e2e/**` |
| external consumer files | 72 | `seo-system` 45, `tappi` 27 |

## Appendix B — the workspace-in-path design (superseded)

Earlier proposal: `/workspaces/{workspace_id}/tables/{table_id}/…` for all 21 routes, with
`workspace_id` mandatory in the path, `GET /workspaces_tables` replacing `GET /sidebar` and
`GET /tables`, UUID-only workspace segments, and no name resolution in the API.

It solves the same collision and the identifier rules are identical, but it leaves
`table_id` as a renameable slug acting as the primary key, so a rename still invalidates
every stored URL, blob key and LQL reference — and it forces every consumer (including the
72 externally-owned files) to rewrite URLs. Kept here because the invariant set in that
document (canonical ids only, names are a UI concern, 404 for unreachable) carries over
unchanged into §3.

## Open questions

1. Compatibility window length — one release (proposed), or until `tappi` / `seo-system`
   finish migrating? Reads are lenient during the window, writes are not.
2. Do we keep `workspace_id` in the `rows` PK forever? Proposed: yes — it is what RLS and the
   per-column indexes filter on, and removing it is a second rewrite for symmetry only.
3. Rename vs stored LQL: rewrite `blocks[].lql` strings on rename (a trigger or a service
   call), or accept that renaming breaks dashboards until the user edits them? Proposed:
   rewrite on rename, in the same transaction as the name change, once LQL is keyed by name.
4. Should `table_name` be case-normalized (`lower()`) like today's slug, or preserve the
   user's casing with a uniqueness index on `lower(table_name)`? Proposed: preserve casing,
   unique on `lower(table_name)` — it is a display name now.
