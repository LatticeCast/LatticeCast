# LLM Context - Dashboard View

## Overview

Dashboard is a fourth view type (alongside Table/Kanban/Timeline). It renders **aggregates** over rows via LatticeQL widget queries — counts, sums, group-bys — not raw rows.

## View Config Shape (stored in `tables.views` JSONB)

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
3. `lattice_ql.compile(lql, schema, workspace_id)` → `(sql, params)`
4. `await session.execute(text(sql), params)` via `get_rls_session`
5. Return rows as JSON array

Files: `router/api/dashboard.py` (endpoint), `repository/dashboard.py` (compile + execute), `config/lattice_ql.py` (schema cache).

## LatticeQL Integration

```python
# config/lattice_ql.py
from lattice_ql import compile  # installed from GitHub release wheel (v0.3.3)

async def get_workspace_schema(workspace_id, session) -> dict:
    key = f"lql_schema:{workspace_id}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    schema = await build_schema(workspace_id, session)
    await redis.setex(key, 60, json.dumps(schema))
    return schema
```

**Adding new primitives to LatticeQL:** done in sibling repo `../LatticeQL`. Backend consumes published wheel only — no Rust toolchain here.

## Adding a New Chart Kind

1. **TS type** — add `"scatter"` to `ChartKind` union in `lib/types/dashboard.ts`
2. **Component** — create `lib/components/dashboard/widgets/ScatterWidget.svelte`; accepts `data: Row[]` + `binding: WidgetBinding` props
3. **Registry** — add to `DashboardView.svelte` chart selector (`chart === "scatter" → ScatterWidget`)
4. **Backend binding** — no change needed; `binding` is passed through as-is; component maps columns

Chart library: `chart.js` via `svelte-chartjs`. Keep all data-transform logic in `lib/dashboard/` TS modules; `.svelte` files configure and render only.
