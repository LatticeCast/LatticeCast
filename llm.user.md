# Users and Workspace Access

- `auth.users`: UUID identity/role; `gdpr.user_info`: PII; `gdpr.user_password`: bcrypt hash.
- Application role (`user`/`admin`) is independent of workspace level (`read`/`write`/`owner`).
- PostgreSQL stores workspace permissions as action rows; the API exposes the highest level.
- Owners manage members; the last owner cannot be removed/demoted.
- Member UI calls `lib/backend/workspaces.ts` and updates `workspace_members.store.ts` from the returned level.
