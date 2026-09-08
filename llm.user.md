# Users and Workspace Access

- `auth.users`: UUID identity/role; `gdpr.user_info`: PII; `gdpr.user_password`: bcrypt hash.
- Application role (`user`/`admin`) is independent of workspace level (`read`/`write`/`owner`).
- PostgreSQL stores workspace permissions as action rows; the API exposes the highest level.
- RLS answers "what may I do" on its own: a member reads their own action rows, so the backend derives a level by querying `workspace_members`, never by asking a permission function.
- Owners manage members; the last owner cannot be removed/demoted. Reading another member's grants requires `owner`.
- Member UI calls `lib/backend/workspaces.ts` and updates `workspace_members.store.ts` from the returned level.
