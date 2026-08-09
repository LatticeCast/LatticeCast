# LatticeCast — Browser Snapshot Guide

Use snapshots to verify the rendered result of frontend changes against the
real stack. The `e2e` service drives remote Chromium in the `browser` service;
both share `.browser/` as `/output`.

## Setup

```bash
docker compose up -d
docker compose --profile test up -d browser e2e
```

Chromium and the E2E client use host networking. Navigate to the public URL
from `BASE_URL` (local default `http://localhost:13491`), not an internal
Compose service hostname.

## Authentication

Use the same flow as `e2e/e2e_base.py`:

1. Obtain a real token from `POST /api/v1/login/password`.
2. Call `seed_login_info(page, token, user_name, role)` before the first
   navigation, or reproduce its `localStorage.loginInfo` shape exactly.
3. Ensure that user has access to the target workspace.

Do not treat a bare user name as a bearer token and do not automate the login UI
unless login itself is the feature under test.

## Capture Rules

- Wait for feature-specific observable state: a stable URL, successful response,
  visible locator, or derived GUI value.
- Never use a fixed sleep to guess readiness.
- Prove the requested feature, not only that the application shell loaded.
- Use a deterministic viewport and descriptive filenames.
- Write directly to `/output/<name>.png`; it appears at `.browser/<name>.png`.
- Do not use `docker cp`.

## Recommended Pattern

Reuse `connect_browser`, `login`, and `seed_login_info` from
`e2e/e2e_base.py`, create a fresh page, navigate, wait for the target locator,
capture to `/output`, then close the page/browser cleanly.

For repeatable snapshots, add or extend a pytest test and run:

```bash
docker compose --profile test exec e2e pytest path/to/test.py -v --snapshot
```

For a one-off investigation, place the script under `.tmp/` and pipe it into
the E2E container. Do not leave credentials in the script or artifact name.

## Output

`.browser/` is evidence and debug output, not application source. Inspect the
image after capture and report what visible state it proves. Read
`.agent-skills/developing/debug-frontend/SKILL.md` for the full debugging
workflow.
