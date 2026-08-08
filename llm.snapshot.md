# Browser Snapshot Guide

## Setup

The `browser` service runs Playwright's remote Chromium server on the host
network. The `e2e` container connects through `BROWSER_WS`; Chromium sees
`localhost:13491` exactly like a real user's browser.

Screenshots write to `.browser/`, mounted as `/output` in the browser service.

```bash
docker compose --profile test up -d browser e2e
```

## Login

Auth is stored in `localStorage` key `loginInfo`. Obtain a real password-login
JWT, then inject the same shape used by `e2e/e2e_base.py`:

```python
import json
import os
import requests
from playwright.sync_api import sync_playwright

base = os.environ.get("BASE_URL", "http://localhost:13491").rstrip("/")
token = requests.post(
    f"{base}/api/v1/login/password",
    json={"user_name": "lattice", "password": ""},
    timeout=10,
).json()["access_token"]
LOGIN_INFO = json.dumps({
    "provider": "none",
    "accessToken": token,
    "userInfo": {"sub": token, "email": "lattice@e2e.local", "name": "lattice"},
    "role": "admin",
})

with sync_playwright() as p:
    browser = p.chromium.connect(os.environ["BROWSER_WS"])
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.add_init_script(
        f"localStorage.setItem('loginInfo', {json.dumps(LOGIN_INFO)});"
    )
    page.goto(f"{base}/{{workspace_id}}/{{table_id}}")
    page.wait_for_timeout(4000)
    page.screenshot(path="/output/my_screenshot.png")
    page.close()
    browser.close()
```

### Login user: `lattice`

Use `POST /api/v1/login/password` for the `lattice` dev user; a bare username
is not the current bearer-token format.

The user must be a workspace member to see tables. If "Failed to fetch" appears, the user isn't a member of that workspace.

### data-testid attributes on login page

- `data-testid="login-userid"` — username input
- `data-testid="login-start"` — submit button

## Rules

1. **Always use `localhost:13491`** — the browser container uses `network_mode: host`, same as a real user
2. **Never use `docker cp`** — screenshots go to `/output` which is mounted as `.browser/`
3. **Inject localStorage, don't fill the login form** — faster and matches E2E fixtures
4. **Use a real JWT** from `/api/v1/login/password`
5. **`wait_for_timeout(4000)`** after navigation — give SvelteKit time to hydrate and fetch data

## Running a snapshot

```bash
docker compose exec -T e2e python3 -c "
import json
from playwright.sync_api import sync_playwright
# ... script here ...
" 2>&1
```

Or write a temporary script under `./.tmp/` and pipe it to Python in the
E2E container:
```bash
docker compose exec -T e2e python3 - < .tmp/snapshot.py
```

## Output

Screenshots go to `.browser/` on the host (= `/output` in container).

```
.browser/
├── _old/           # archived screenshots from previous workers
├── doc_z_01_table.png
└── doc_z_02_popup.png
```
