# PM System — Git Integration Design

## Overview

The PM table is a standard LatticeCast table (JSONB + GIN) with a **git sync** feature. The backend is stateless — it mounts a shared volume (Docker volume, AWS EFS, or NFS) containing git repos. On sync trigger, it runs `git fetch --all && git pull`, parses branches, and updates ticket rows.

## Architecture

```
Backend (stateless)
  ├── mounts /repos/ volume (docker volume / EFS / NFS)
  ├── /api/pm/sync        → git fetch + git pull + parse branches + update tickets
  ├── /api/pm/test_status → test script writes pass/fail per ticket
  └── reads /repos/<name>/ as plain folders

Volume (shared storage)
  ├── project_alpha/      # cloned repo
  ├── project_beta/
  └── ...
```

Backend just sees a folder. It doesn't care how it's mounted:
- Dev: `docker volume` or bind mount `./repos/:/repos/`
- Prod: AWS EFS, NFS, or any shared filesystem

## Ticket Key Format

Ticket keys use **snake_case + number** for easy parsing:

```
[a-z_]+[0-9]+

Examples:
  lc_42
  be_108
  fe_15
  infra_3
```

- Only lowercase `a-z`, underscore `_`, and digits `0-9`
- Prefix is user-defined per table (e.g. `lc`, `be`, `fe`)
- Simple to parse, grep, and match in branch names

## Branch Matching — User-Defined Regex

The branch naming rule is **not hardcoded**. Each PM table has a `branch_pattern` field in its config. The pattern uses `${var}` template variables that expand to regex capture groups.

### Pattern Syntax

Use `${var}` for named captures. The system replaces them with regex groups:

| Variable | Expands To | Meaning |
|---|---|---|
| `${type}` | `(\w+)` | Branch type (feat, fix, chore...) |
| `${key}` | `([a-z_]+\d+)` | Ticket key (snake_case + number) |
| `${desc}` | `(.+)` | Description (any text) |
| `${num}` | `(\d+)` | Numeric ID |
| `${jira}` | `([A-Z]+-\d+)` | JIRA-style key (PROJ-42) |

### Default pattern

```
${type}/${key}/${desc}
```

Expands to regex: `^(\w+)/([a-z_]+\d+)/(.+)$`

Matches: `feat/lc_42/add_user_profile` → key = `lc_42`

### User can set custom patterns

| Pattern | Expanded Regex | Example Branch |
|---|---|---|
| `${type}/${key}/${desc}` (default) | `^(\w+)/([a-z_]+\d+)/(.+)$` | `feat/lc_42/add_profile` |
| `feature/#${num}` | `^feature/#(\d+)$` | `feature/#001234` |
| `feature/${jira}-${desc}` | `^feature/([A-Z]+-\d+)-(.+)$` | `feature/PROJ-42-add-thing` |
| `${key}` | `^([a-z_]+\d+)$` | `lc_42` |
| `${type}/issue-${num}/${desc}` | `^(\w+)/issue-(\d+)/(.+)$` | `fix/issue-99/hotfix` |

Users can also write raw regex directly by prefixing with `regex:`:

```
regex:^(\w+)/([a-z_]+\d+)/(.+)$
```

### Config

Stored in table options JSONB:

```json
{
  "pm_config": {
    "repo_path": "project_alpha",
    "branch_pattern": "${type}/${key}/${desc}",
    "ticket_key_var": "key",
    "main_branch": "main"
  }
}
```

- `branch_pattern` — template with `${var}` or `regex:` prefix for raw regex
- `ticket_key_var` — which `${var}` is the ticket key (default: `key`)
- System extracts the named capture matching `ticket_key_var` and looks up the ticket row

## Ticket Hierarchy — User-Defined

Like Jira's Epic → Story → Issue, but **user defines the levels** via tables and links:

- Create separate tables: `Epics`, `Stories`, `Issues`
- Or use a single table with a `level` select column: `epic`, `story`, `issue`
- Link parent via a `parent_key` text column referencing another ticket key
- The system doesn't enforce hierarchy — users design it with columns

This keeps the schema flexible. A solo developer might just have one flat table. A team might have 3-level hierarchy.

## Git Sync Flow

```
1. User triggers: curl -X POST /api/pm/sync
2. Backend reads /repos/<repo>/ folder
3. Run: git fetch --all --prune && git pull
4. Parse: git branch -r → list all remote branches
5. Parse: git branch -r --merged origin/<main_branch> → list merged branches
6. For each branch:
   a. Apply user's branch_regex
   b. Extract ticket key (capture group)
   c. Match to row in PM table where Key column == ticket key
7. Update ticket Status column:
   - No matching branch → "pending"
   - Branch exists, not merged → "in_progress"
   - Branch merged → "merged"
8. Return sync result summary
```

## Auto-Status Detection

Git sync only detects **3 states**. Everything beyond `merged` is manual.

| Branch State | How Detected | Ticket Status |
|---|---|---|
| No branch | No regex match in `git branch -r` | `pending` |
| Branch exists, not merged | In `git branch -r`, not in `--merged main` | `in_progress` |
| Branch merged | In `git branch -r --merged main` | `merged` |

## Status Lifecycle

`merged` is NOT `done`. After merge, the ticket goes through testing:

```
pending → in_progress → merged → sit → uat → done
                                   ↓         ↓
                                 fixing ←── fixing
                                   ↓
                                 merged (re-merge after fix)
```

| Status | Set By | Meaning |
|---|---|---|
| `pending` | git sync (no branch) | Not started |
| `in_progress` | git sync (branch exists) | Developer working |
| `merged` | git sync (branch merged) | Code merged to main |
| `sit` | manual | System Integration Testing |
| `uat` | manual | User Acceptance Testing |
| `fixing` | test script or manual | Test failed, developer fixing |
| `done` | manual only | All tests pass, verified, closed |

**Key rule:** `done` is always set manually. The system never auto-closes a ticket. Only a human confirms "this is done."

When a test fails (SIT or UAT), status is set to `fixing`. The developer creates a new fix branch, which git sync detects and updates to `in_progress` → `merged` again → re-test.

## Test Status — Script-Driven

Tests are **not auto-detected**. The developer who creates the branch manually triggers tests. A test script writes results back via curl, and can also update the ticket status to `fixing` on failure:

```bash
# Test pass — only updates test_status column
curl -X POST http://localhost:5000/api/pm/test_status \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"table_id": "...", "ticket_key": "lc_42", "test_status": "pass"}'

# Test fail — updates test_status AND sets ticket status to "fixing"
curl -X POST http://localhost:5000/api/pm/test_status \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"table_id": "...", "ticket_key": "lc_42", "test_status": "fail", "message": "3 tests failed"}'
```

The test script can be a CI step, a git hook, or a manual command. The PM system just receives the result.

On `fail`, the system also sets the ticket status to `fixing` automatically. The developer then creates a fix branch → git sync detects `in_progress` → merge → re-test.

| Test State | test_status | Ticket Status Effect |
|---|---|---|
| Tests pass | `"pass"` | No status change (stay at sit/uat) |
| Tests fail | `"fail"` | Auto-set status to `"fixing"` |
| Not tested | `null` | — |

## API Endpoints

```bash
# Trigger sync (git fetch + update tickets)
POST /api/pm/sync
POST /api/pm/sync/{repo_name}

# Test status update (from test scripts)
POST /api/pm/test_status

# List repos in mounted volume
GET  /api/pm/repos

# Get repo branches
GET  /api/pm/repos/{name}/branches
```

### Sync Example

```bash
curl -X POST http://localhost:5000/api/pm/sync/project_alpha \
  -H "Authorization: Bearer $TOKEN"

# Response
{
  "repo": "project_alpha",
  "branches_found": 12,
  "tickets_updated": 5,
  "updates": [
    {"key": "lc_42", "status": "in_progress", "branch": "feat/lc_42/add_profile"},
    {"key": "lc_15", "status": "done", "branch": "fix/lc_15/login_bug"}
  ]
}
```

## PM Table Template

### `pm-template.json`

```json
[
  {"name": "key",          "type": "text",   "options": {"width": 100},  "position": 0},
  {"name": "title",        "type": "text",   "options": {"width": 300},  "position": 1},
  {"name": "status",       "type": "select", "options": {"choices": [
    {"value": "pending",      "color": "bg-gray-100"},
    {"value": "in_progress",  "color": "bg-blue-100"},
    {"value": "merged",       "color": "bg-indigo-100"},
    {"value": "sit",          "color": "bg-yellow-100"},
    {"value": "uat",          "color": "bg-orange-100"},
    {"value": "fixing",       "color": "bg-red-100"},
    {"value": "done",         "color": "bg-green-100"}
  ]}, "position": 2},
  {"name": "type",         "type": "select", "options": {"choices": [
    {"value": "feat",  "color": "bg-green-100"},
    {"value": "fix",   "color": "bg-red-100"},
    {"value": "chore", "color": "bg-gray-100"},
    {"value": "test",  "color": "bg-purple-100"},
    {"value": "docs",  "color": "bg-blue-100"}
  ]}, "position": 3},
  {"name": "priority",     "type": "select", "options": {"choices": [
    {"value": "p0_critical", "color": "bg-red-100"},
    {"value": "p1_high",     "color": "bg-orange-100"},
    {"value": "p2_medium",   "color": "bg-yellow-100"},
    {"value": "p3_low",      "color": "bg-green-100"}
  ]}, "position": 4},
  {"name": "assignee",     "type": "text",   "options": {"width": 120},  "position": 5},
  {"name": "branch",       "type": "text",   "options": {"width": 250},  "position": 6},
  {"name": "repo",         "type": "text",   "options": {"width": 150},  "position": 7},
  {"name": "test_status",  "type": "select", "options": {"choices": [
    {"value": "pass", "color": "bg-green-100"},
    {"value": "fail", "color": "bg-red-100"}
  ]}, "position": 8},
  {"name": "parent_key",   "type": "text",   "options": {"width": 100},  "position": 9},
  {"name": "level",        "type": "select", "options": {"choices": [
    {"value": "epic",  "color": "bg-purple-100"},
    {"value": "story", "color": "bg-blue-100"},
    {"value": "issue", "color": "bg-gray-100"}
  ]}, "position": 10},
  {"name": "tags",         "type": "tags",   "options": {"choices": [
    {"value": "backend",  "color": "bg-blue-100"},
    {"value": "frontend", "color": "bg-green-100"},
    {"value": "database", "color": "bg-purple-100"},
    {"value": "devops",   "color": "bg-orange-100"}
  ]}, "position": 11},
  {"name": "endpoint",     "type": "url",    "options": {"width": 200},  "position": 12},
  {"name": "due_date",     "type": "date",   "options": {},              "position": 13},
  {"name": "notes",        "type": "text",   "options": {"width": 300},  "position": 14}
]
```

## Docker / Deployment

### Dev (docker-compose)

```yaml
backend:
  volumes:
    - ./backend/:/app/
    - ./migration/:/migration/:ro
    - repos_volume:/repos          # named volume
```

### Prod (AWS ECS + EFS)

```
EFS filesystem → mounted at /repos in backend container
Backend is stateless → scales horizontally
All instances see same /repos via EFS
```

Backend doesn't clone repos — it expects them to already exist in `/repos/`. A setup script or admin endpoint handles initial `git clone`.

## OpenAPI Integration

PM table view fetches `openapi.json` from a configured URL:

```json
{
  "pm_config": {
    "openapi_url": "http://backend:5000/openapi.json"
  }
}
```

Frontend shows endpoint list alongside tickets. Tickets with matching paths/tags show implementation status.

## Table Config (stored in tables.options JSONB)

```json
{
  "pm_config": {
    "repo_path": "project_alpha",
    "branch_regex": "^(\\w+)/([a-z_]+\\d+)/(.+)$",
    "ticket_key_group": 2,
    "main_branch": "main",
    "ticket_prefix": "lc",
    "openapi_url": null
  }
}
```

All PM-specific config lives in the table's `options` JSONB — no extra tables needed.
