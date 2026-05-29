# LLM Context — Dashboard View

## Overview

Dashboard is a fourth view type (alongside Table/Kanban/Timeline). It renders **aggregates** over rows via LatticeQL block queries — counts, sums, group-bys — not raw rows. Chart library: **ECharts** (replaced chart.js). Terminology: **blocks** (not widgets).

## View Config Shape (`table_views.config` for type=dashboard)

```jsonc
{
  "layout": [
    { "id": "b1", "x": 0, "y": 0, "w": 6, "h": 4 },
    { "id": "b2", "x": 6, "y": 0, "w": 6, "h": 4 }
  ],
  "blocks": {
    "b1": {
      "kind": "chart",
      "title": "Pipeline by stage",
      "lql": "table(\"Deals\") | group_by(...) | aggregate(...)",
      "echarts": { "xAxis": {"type":"category"}, "series": [{"type":"bar","encode":{"x":"stage","y":"value"}}], "dataset": [{"$inject":"rows"}] }
    },
    "b2": { "kind": "number", "title": "Total Deals", "lql": "...", "field": "total", "format": null }
  }
}
```

## Block Kinds

| Kind | Model (BE) | Fields | FE Component |
|------|-----------|--------|--------------|
| `chart` | `ChartBlock` | `title`, `lql`, `echarts` (ECharts option JSON; use `{"$inject":"rows"}` for data) | `ChartBlock.svelte` → `EChart.svelte` |
| `number` | `NumberBlock` | `title`, `lql`, `field`, `format?` | `NumberBlock.svelte` |
| `list` | `ListBlock` | `title`, `lql`, `columns: [{key,label}]` (empty = auto-detect from rows) | `ListBlock.svelte` |

Discriminated union on `kind` field — BE: `models/view.py` (`Block = ChartBlock | NumberBlock | ListBlock`), FE: `lib/types/dashboard.ts`.

## Block Query Endpoint

```
POST /api/v1/tables/{table_id}/views/{view_name}/blocks/{block_id}/query
Body: { "params": {} }
→ { "rows": [ { dim_0: "qualified", value: 42000 }, ... ] }
```

**Note:** path uses `view_name` (string), not `view_id` (int). Resolved via `TableViewRepository.get_by_name()`.

Flow:
1. `_get_table_for_member()` — resolve table, verify workspace membership
2. Load view by name → check `type == "dashboard"` → read `config.blocks[block_id].lql`
3. `compile_lql(lql, workspace_id, session)` — build schema (Valkey cache 60s), compile to SQL, inline `$1` as workspace UUID, rewrite `table_name` subquery to direct `table_id` filter
4. `DashboardRepository.execute(session, sql, params)` — `text(sql)` via RLS session
5. Return `{"rows": [...]}`

Files: `router/api/dashboard.py`, `repository/dashboard.py`, `config/lattice_ql.py`.

## LatticeQL Integration

```
lattice-ql @ git+https://github.com/latticeCast/LatticeQL@v0.2.0
```

`config/lattice_ql.py`: `compile(lql, schema)` → SQL. Schema built from `__schema__` rows per table, cached in Valkey 60s (`lql:schema:{workspace_id}`). `invalidate_schema_cache()` exported for column changes.

Adapter rewrites: `_inline_workspace()` (replace `$1`), `_fix_table_name()` (subquery → direct filter). Upstream is pure Python (hatchling) — bump git ref in `backend/pyproject.toml` to upgrade.

## Frontend Architecture

```
lib/charts/
  EChart.svelte        — generic echarts wrapper (init, resize, theme-aware, $effect re-render)
  inject.ts            — applyInjects(): walk echarts option JSON, replace {"$inject":"rows"} with {source: rows}
  index.ts             — re-exports EChart + applyInjects

lib/components/dashboard/
  DashboardView.svelte — grid layout (CSS grid 12-col), inline grid-column/grid-row styles, JSON editor for config
  blocks/
    Block.svelte       — dispatcher: routes block.kind → ChartBlock | NumberBlock | ListBlock
    ChartBlock.svelte  — fetches rows, applies injects, renders EChart
    NumberBlock.svelte  — fetches rows, extracts rows[0][field], renders big number
    ListBlock.svelte   — fetches rows, renders <table>; auto-derives columns if block.columns is empty

lib/api/dashboard.ts   — fetchBlockRows(tableId, viewName, blockId) → POST to query endpoint
lib/types/dashboard.ts — TS types mirroring BE models (BlockKind, LayoutEntry, *Block, DashboardConfig, DashboardView, BlockRow)
```

## Adding a New Block Kind

1. **BE model** — add `FooBlock(BaseModel)` in `models/view.py`, add to `Block` union
2. **FE type** — add `FooBlock` interface in `lib/types/dashboard.ts`, add to `Block` union + `BlockKind`
3. **FE component** — create `blocks/FooBlock.svelte`, call `fetchBlockRows()`, render
4. **Dispatcher** — add `{:else if block.kind === 'foo'}` branch in `Block.svelte`
5. **No backend route change** — same query endpoint, new kind is config-only
