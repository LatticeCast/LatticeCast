# LatticeCast — Users and Workspace Access

User identity, application role, workspace membership, and login credential are
separate concepts. See `llm.arch.auth.md` for token verification and engines.

## User Data

| Relation | Owns |
|---|---|
| `auth.users` | `user_id UUID`, application role, audit timestamps |
| `gdpr.user_info` | email, unique `user_name`, per-user UI config |
| `gdpr.user_password` | optional bcrypt hash, isolated from app-role reads |

The UUID is identity. `user_name` and email are lookup/display fields and are
not workspace or S3 key components.

## Application Roles vs Workspace Levels

- Application role is `user` or `admin`; admin gates `/admin/users`.
- Workspace level is `read`, `write`, or `owner`; it governs one workspace.
- Being an application admin does not replace workspace membership/RLS.
- The API returns one highest workspace level, while PostgreSQL stores one row
  per granted action:

| API level | Stored actions |
|---|---|
| `read` | `read` |
| `write` | `read`, `write` |
| `owner` | `read`, `write`, `owner` |

Owners manage membership. The backend prevents removal or demotion of the last
owner.

## User Lifecycle

- Tokens resolve only registered local users; authentication does not
  auto-create identities.
- Admin user creation writes identity and PII through the manager session and
  bootstraps initial workspace access.
- Self-service endpoints expose current user/config, email update, and password
  set/change.
- Workspace invitations resolve a target by UUID, `user_name`, or email.
- GDPR-sensitive data remains in the `gdpr` schema; do not move credentials into
  broadly readable user-info data.

## Frontend Member Flow

```text
members page event
  -> lib/backend/workspaces.ts
  -> workspace member endpoint
  <- MemberFullResponse with level
  -> workspace_members.store.ts cache
  -> page $derived member rows and controls
```

New UI behavior must use the response-provided `level` and update the store
through its helpers. Do not create three visible rows for the three database
actions and do not infer the new level from the request.

## Main Files

| Concern | Source |
|---|---|
| Models | `backend/src/models/user.py`, `backend/src/models/workspace.py` |
| Persistence | `backend/src/repository/user.py`, `backend/src/repository/workspace.py` |
| Login/self service | `backend/src/router/api/auth.py` |
| Admin users | `backend/src/router/api/admin/users.py` |
| Workspace members | `backend/src/router/api/workspaces.py` |
| FE controller/cache | `frontend/src/lib/backend/workspaces.ts`, `frontend/src/lib/stores/workspace_members.store.ts` |
| Members page | `frontend/src/routes/[workspace_id]/members/+page.svelte` |

Use API models/OpenAPI for exact payload fields. Keep this document focused on
the identity and authorization boundaries.
