# LatticeCast — E2E Tests

`e2e/` uses pytest, requests, and a remote Playwright Chromium instance against
the real frontend, backend, PostgreSQL, and MinIO. Tests are not mocked unit
tests.

## Run

```bash
docker compose up -d
docker compose --profile test up -d --build browser e2e
docker compose --profile test exec e2e pytest -v
docker compose --profile test exec e2e pytest tables/test_row_update.py -v
docker compose --profile test exec e2e pytest -v --snapshot
```

`BASE_URL` selects the tested deployment. `BROWSER_WS` selects the remote
browser. Their Compose defaults target the local host-network stack.

## Test Architecture

| Path | Purpose |
|---|---|
| `e2e/e2e_base.py` | Base URL, login, authenticated request, browser connection, auth seeding |
| `e2e/conftest.py` | Shared browser/page/user/workspace/table fixtures |
| `e2e/auth/` | Login, self-service config, and admin behavior |
| `e2e/workspace/` | Workspace CRUD, sidebar, member levels and revocation |
| `e2e/tables/` | Table, column, row, filter/edit, and document behavior |
| `e2e/table_views/` | Views, Kanban, Timeline, and Workflow behavior |
| `e2e/template/` | Template seed contracts |

Fixtures create isolated workspaces/tables and clean them up. Prefer existing
fixtures and `e2e_base.py` helpers over reimplementing login or HTTP boilerplate.

## Test Rules

- Exercise behavior through public API/UI boundaries.
- Use a real token and seed `localStorage.loginInfo` before first navigation.
- Wait for a URL, response, locator, or derived GUI state; never use a fixed
  sleep as synchronization.
- Assert the final visible state after the controller response updated stores.
  An HTTP success alone does not prove the frontend flow works.
- Keep each test focused and use unique workspace/table names.
- Capture screenshots only when they help verify UI state; artifacts go to
  `.browser/` through `/output`.

## Choosing Scope

Start with the smallest affected test, then its package, then the whole suite
when the change crosses shared auth, sidebar, schema, or fixture behavior.
Frontend structural changes also need the checks in `llm.dev.md`.

Read `.agent-skills/developing/e2e/SKILL.md` before adding or restructuring E2E
coverage. See `llm.snapshot.md` for ad-hoc browser evidence.
