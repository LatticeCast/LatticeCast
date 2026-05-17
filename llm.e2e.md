# E2E Tests

## Location

`test-e2e/` — Python scripts using Playwright + requests against the live stack.

## How to Run

```bash
# 1. Start test container (and deps) in background
docker compose --profile test up -d

# 2. Exec into the running container to run all tests
docker compose --profile test exec test-e2e bash -c \
  'for f in /scripts/e2e_test_*.py; do echo "=== $(basename $f) ==="; python $f || echo "FAIL: $f"; done'

# Run a single test
docker compose --profile test exec test-e2e python /scripts/e2e_test_column_add.py
```

Requires the full stack running (`docker compose up -d`) plus the `browser` container.

## Architecture

- `e2e_base.py` — shared bootstrap: `BASE` URL, `login()`, `api()`, `seed_login_info()`, `connect_browser()`
- `e2e_test_*.py` — one file per test topic
- Connects to Playwright browser container via `BROWSER_WS` websocket
- Tests hit the real backend API + real DB (not mocked)

## Test Coverage

| Area | Tests |
|------|-------|
| Auth | `admin_create_user`, `auth_admin_only`, `me_config_darkmode`, `me_email_change` |
| Columns | `add`, `delete`, `rename`, `checkbox_type`, `doc_type`, `tags_type`, `url_type`, `option_add_remove`, `option_colors` |
| Rows | `create`, `delete`, `update`, `doc_round_trip`, `filter_json` |
| Views | `create`, `delete`, `rename`, `default`, `order` |
| Table views | `col_hide`, `col_order`, `col_resize`, `filter`, `inline_edit`, `search` |
| Kanban | `add_row`, `card_fields`, `drag_card`, `groupby` |
| Timeline | `color_by`, `granularity`, `groupby` |
| Templates | `pm`, `crm` |
| Workspaces | `create`, `delete_cascade`, `rename`, `table_create`, `member_invite`, `member_remove`, `member_role` |
| Other | `seo_framework` |

## Docker Setup

```yaml
# docker-compose.yml profiles:
# - test: runs test-e2e container
# - browser: runs Playwright chromium server

test-e2e:
  profiles: [test]
  context: ./test-e2e
  # connects to browser container via BROWSER_WS
```

## Writing New Tests

1. Create `test-e2e/e2e_test_<name>.py`
2. Import from `e2e_base`: `from e2e_base import BASE, login, api, seed_login_info, connect_browser, fatal`
3. Use `api("GET", "/api/v1/...", token)` for API calls
4. Use Playwright for browser interactions via `connect_browser(pw)`
5. Exit with `fatal("message")` on failure
