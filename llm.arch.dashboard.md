# LLM Context - Dashboard View

## Overview

Dashboard is a fourth view type (alongside Table/Kanban/Timeline). It renders **aggregates** over rows via LatticeQL widget queries — counts, sums, group-bys — not raw rows.

## View Config Shape (stored in the dashboard view's row in `public.table_views`)

```jsonc
{
  "name": "Sales Dashboard",
  "type": "dashboard",
  "config": {
    "layout": [
      { "widget_id": "w1", "x": 0, "y": 0, "w": 6, "h": 4 },
      { "widget_id": "w2", "x": 6, "y": 0, "w": 6, "h": 4 }
    ],
    "widgets": {
      "w1": {
        "title": "Pipeline by stage",
        "chart": "bar",          // number | bar | pie | line | list
        "lql": "table(\"Deals\") | group_by((r)->{r.status}) | aggregate(@{\"value\": sum(r.amount)})",
        "binding": { "x": "dim_0", "y": "value" }
      }
    }
  }
}
```

Dashboard configs are stored/updated via existing view CRUD endpoints — no new view API needed.

## Widget Query Endpoint

```
POST /api/v1/tables/{tid}/views/{view_name}/widgets/{wid}/query
Authorization: Bearer <token>
→ [ { dim_0: "qualified", value: 42000 }, ... ]
```

Flow:
1. Load table row → read `views[view_name].config.widgets[wid].lql`
2. Build workspace schema dict (table column map) → cache in Valkey 60s
3. `lattice_ql.compile(lql, schema)` → SQL string with `$1` for workspace_id
4. Adapter inlines `$1` as `'<workspace_uuid>'` and rewrites the
   `table_id = (SELECT … FROM tables WHERE table_name = …)` subquery to a
   direct `table_id = '…' AND workspace_id = '…'` filter (LatticeCast uses
   the table name as the table_id PK)
5. `await session.execute(text(sql))` via `get_rls_session` — RLS handles
   the workspace-membership check
6. Return rows as JSON array

Files: `router/api/dashboard.py` (endpoint), `repository/dashboard.py` (execute), `config/lattice_ql.py` (compile + schema cache + adapter).

## LatticeQL Integration

```python
# config/lattice_ql.py
from lattice_ql import compile as _compile
from lattice_ql.error import LatticeQLError
# installed via: lattice-ql @ git+https://github.com/latticeCast/LatticeQL@v0.2.0
```

**Adding new primitives to LatticeQL:** work in the upstream repo
(https://github.com/latticeCast/LatticeQL), tag a new version, bump the
git ref in `backend/pyproject.toml`. Upstream is pure Python (hatchling
build) — no Rust toolchain involved.

## Adding a New Chart Kind

1. **TS type** — add `"scatter"` to `ChartKind` union in `lib/types/dashboard.ts`
2. **Component** — create `lib/components/dashboard/widgets/ScatterWidget.svelte`; accepts `data: Row[]` + `binding: WidgetBinding` props
3. **Registry** — add to `DashboardView.svelte` chart selector (`chart === "scatter" → ScatterWidget`)
4. **Backend binding** — no change needed; `binding` is passed through as-is; component maps columns

Chart library: `chart.js` via `svelte-chartjs`. Keep all data-transform logic in `lib/dashboard/` TS modules; `.svelte` files configure and render only.
