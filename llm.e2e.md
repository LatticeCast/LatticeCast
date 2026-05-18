# E2E Tests

## Location

`test-e2e/` — pytest + Playwright + requests against the live stack.

## How to Run

```bash
# 1. Start test container (rebuild if deps changed)
docker compose --profile test up -d --build test-e2e

# 2. Run all tests
docker compose --profile test exec test-e2e pytest -v

# Run a single package
docker compose --profile test exec test-e2e pytest tables/ -v

# Run a single test
docker compose --profile test exec test-e2e pytest tables/test_column_add.py -v

# With screenshots
docker compose --profile test exec test-e2e pytest -v --snapshot
```

Requires the full stack running (`docker compose up -d`) plus the `browser` container.

## Architecture

- `conftest.py` — shared pytest fixtures: `browser`, `page`, `authed_page`, `admin_token`, `workspace`, `pm_table`
- `e2e_base.py` — low-level helpers: `BASE` URL, `login()`, `api()`, `seed_login_info()`, `connect_browser()`
- `{package}/test_*.py` — one file per test topic, uses pytest fixtures + assertions
- Connects to Playwright browser container via `BROWSER_WS` websocket
- Tests hit the real backend API + real DB (not mocked)

## Test Packages

| Package | Tests |
|---------|-------|
| `auth/` | `admin_create_user`, `admin_only`, `me_config_darkmode`, `me_email_change` |
| `tables/` | `column_add`, `column_delete`, `column_rename`, `column_checkbox_type`, `column_doc_type`, `column_tags_type`, `column_url_type`, `column_option_add_remove`, `column_option_colors`, `col_order`, `col_resize`, `filter`, `inline_edit`, `search`, `row_create`, `row_delete`, `row_update`, `row_doc_round_trip`, `row_filter_json`, `table_create` |
| `table_views/` | `views_create`, `views_delete`, `views_default`, `views_order`, `views_rename`, `kanban_add_row`, `kanban_card_fields`, `kanban_drag_card`, `kanban_groupby`, `timeline_color_by`, `timeline_granularity`, `timeline_groupby` |
| `template/` | `pm`, `crm`, `seo_framework` |
| `workspace/` | `create`, `delete_cascade`, `rename`, `member_invite`, `member_remove`, `member_role` |

## Fixtures (`conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `browser` | session | Playwright browser connected via `BROWSER_WS` |
| `page` | function | Fresh browser page (1400x900) |
| `admin_token` | session | Login token for `lattice` user |
| `authed_page` | function | Page with `loginInfo` seeded in localStorage |
| `workspace` | function | Creates + tears down a workspace, yields `(ws_id, ws_name)` |
| `pm_table` | function | Creates PM template table, yields `(table_id, ws_id, columns, views)` |

## Writing New Tests

1. Create `test-e2e/{package}/test_<name>.py`
2. Use conftest fixtures by parameter name: `def test_foo(authed_page, workspace, admin_token):`
3. Import helpers from `e2e_base`: `from e2e_base import BASE, api`
4. Use `assert` for verifications (pytest handles failures)
5. Use `--snapshot` flag for Playwright screenshots
