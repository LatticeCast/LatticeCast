# TODO

## ECharts 
use ECharts for CRM system

## Token saving
use anthropic prompt caching.
claude-bot need design caching prompt

## Performance Tuning

- [ ] Evaluate `gin_pending_list_limit` for GIN indexes on JSONB columns (select/tags)
  - Default 64KB may bottleneck during batch imports (CSV/JSON) and PM template creation
  - Consider per-index or session-level increase (e.g. 256KB) for bulk write scenarios
  - Trade-off: higher limit = faster writes, slightly slower queries on pending data
