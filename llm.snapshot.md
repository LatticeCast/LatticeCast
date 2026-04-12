# Browser Snapshot Guide

## Setup

The `browser` service uses `network_mode: host` — Chromium inside the container sees `localhost:13491` exactly like a real user's browser.

Screenshots write to `.browser/` (mounted as `/output`). Container runs as `user: "1000:1000"` so files are owned by the host user, not root.

```bash
docker compose --profile browser up -d browser
```

## Login

Auth is stored in `localStorage` key `loginInfo`. Inject it before navigating:

```python
import json
from playwright.sync_api import sync_playwright

LOGIN_INFO = json.dumps({
    "provider": "none",
    "accessToken": "lattice",  # user identifier (display_id, UUID, or email)
    "userInfo": {"sub": "lattice", "email": "lattice", "name": "Lattice"},
    "role": "user"
})

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1400, "height": 900})
    # 1. Go to base URL first (needed for localStorage domain)
    page.goto("http://localhost:13491")
    # 2. Inject auth
    page.evaluate(f"localStorage.setItem('loginInfo', '{LOGIN_INFO}')")
    # 3. Navigate to target page
    page.goto("http://localhost:13491/{workspace_id}/{table_id}?view=Table")
    page.wait_for_timeout(4000)
    page.screenshot(path="/output/my_screenshot.png")
    b.close()
```

### Login user: `lattice`

Use `accessToken: "lattice"` — this is the default dev user specified in `CLAUDE.md`.

The user must be a workspace member to see tables. If "Failed to fetch" appears, the user isn't a member of that workspace.

### data-testid attributes on login page

- `data-testid="login-userid"` — username input
- `data-testid="login-start"` — submit button

## Rules

1. **Always use `localhost:13491`** — the browser container uses `network_mode: host`, same as a real user
2. **Never use `docker cp`** — screenshots go to `/output` which is mounted as `.browser/`
3. **Files are user-owned** — `user: "1000:1000"` in docker-compose prevents root-owned files
4. **Inject localStorage, don't fill the login form** — faster, more reliable
5. **`wait_for_timeout(4000)`** after navigation — give SvelteKit time to hydrate and fetch data

## Running a snapshot

```bash
docker compose exec browser python3 -c "
import json
from playwright.sync_api import sync_playwright
# ... script here ...
" 2>&1
```

Or write a `.py` file and run:
```bash
docker compose exec browser python3 /app/my_test.py
```

## Output

Screenshots go to `.browser/` on the host (= `/output` in container).

```
.browser/
├── _old/           # archived screenshots from previous workers
├── doc_z_01_table.png
└── doc_z_02_popup.png
```
