# Design Decisions

Intentional tradeoffs that a security/code review can mistake for bugs. Do
not "fix" these without checking with the product owner first — each one
encodes a stated product goal, not an oversight.

## Email lookup is open to every authenticated user

`gdpr.user_info` is SELECT-readable by every `app_user`
(`migration/V20__rls_app_user_read_user_info.sql`, policy
`user_info_app_read ON gdpr.user_info FOR SELECT TO app_user USING (true)`).

- **Why:** workspace invites are by email — adding a member resolves
  `user_email` via `resolve_user_by_email` across the whole user base, not
  just the inviter's own workspace. A self-only or workspace-scoped read
  policy would break that flow entirely.
- **Scope:** email + `user_name` + per-user UI config. Password hashes live
  in a separate table, `gdpr.user_password` (V32), specifically so this
  broad read policy never exposes them.
- Do not narrow this policy to "fix" email enumeration; it is the invite
  mechanism, not a leak.

## Passwordless login is an explicit, admin-only opt-in (V78)

`POST /login/password` (`backend/src/router/api/auth.py`) decides from the
account's `gdpr.user_password` row:

| row                                   | result                             |
| ------------------------------------- | ---------------------------------- |
| `password_hash` set                   | the password must match            |
| no hash, `allow_no_pwd` **TRUE**      | logs in without a password         |
| anything else (no row, NULL, FALSE)   | 401, password login not enabled    |

- **Why:** this reverses the earlier rule that "no password row means no
  check". That made every account created without a password a standing
  open door. Passwordless login is now something an admin chooses per account
  (demo accounts, e2e users), never a side effect of a missing row.
- `allow_no_pwd` is a nullable BOOLEAN with no default, and `password_hash` is
  nullable. Only TRUE opens an account. A CHECK forbids a hash together with
  TRUE. V78 back-fills nothing: accounts that had no row stop logging in until
  an admin opts them in or they set a password.
- Only an admin can set it: `POST /api/v1/admin/users` (`allow_no_pwd`, default
  false) and `PUT /api/v1/admin/users/{email}/allow-no-pwd`. The generic user
  update does not accept it, and no self-service route can. Opting in an
  account that already has a password is a 409.
- Setting a password (`PUT /login/me/password`) clears `allow_no_pwd`.
- bcrypt reads only 72 bytes, so longer passwords and secrets are rejected
  with a 422, not truncated.
- Do not "fix" a locked demo account by treating a missing row as passwordless
  again; opt it in.

## Admin endpoints live in one place

Every endpoint that needs an admin is under `/api/v1/admin/`, and
`require_admin` is applied once, on the parent router in
`backend/src/router/api/admin/__init__.py`. Sub-routers carry no admin check of
their own. `backend/tests/test_admin_routes.py` fails if an `/admin` route lacks
the guard or an admin-only route sits outside `/admin`.

## A workspace may have no owner

Removing or demoting the last owner of a workspace is allowed by product
decision, including an owner doing it to themselves. Zero owners is a valid
state.

- Do not "fix" this in a review by adding a check, constraint or trigger that
  requires an owner, in the API or the database.
- Consequence: only an owner may rename or delete a workspace or manage its
  members, so none of those is possible through the API once it has no owner.

## Workspace names are not unique

Two workspaces may have the same `workspace_name`, by product decision.
`workspace_id` is the identity.

- Do not add a unique constraint or an "already exists" check on create or
  rename.
- An API call that names a workspace by `workspace_name` gets 409 when several
  visible workspaces share it. The server never picks one.
- The web client looks names up from the URL, so it adds a creation-order
  suffix to duplicates, 0-based with the 0 unwritten: `seo`, `seo-1`, `seo-2`
  (`frontend/src/lib/utils/slugs.ts`). A real name keeps itself, so a
  workspace literally called `seo-1` takes that URL and the duplicate moves to
  `seo-2`. Tables follow the same rule. The suffix counts only what the
  signed-in user can see, and it shifts when an earlier namesake is deleted or
  renamed.

## Horizontal scaling direction (planned, not yet implemented)

Recorded ahead of implementation so these aren't rediscovered or
second-guessed mid-migration. Neither is done; both are the intended next
step when scaling past a single backend process / single Postgres instance
becomes necessary.

### Put a transaction-mode connection pooler (e.g. PgBouncer) in front of Postgres

- **Why:** `core/db.py` gives every backend process its own engine
  (`pool_size=5, max_overflow=10`). N backend replicas means N×15 Postgres
  connections — `max_connections` is exhausted well before CPU/memory
  becomes the bottleneck, so the backend cannot actually be scaled out
  horizontally today without this.
- The RLS identity GUC is already transaction-local, specifically so a
  pooler is safe to introduce later without an identity-leak window across
  tenants — see the "RLS IDENTITY HYGIENE" comment in `backend/src/core/db.py`
  for the mechanism, and `backend/tests/test_rls_pool_reset.py` for the
  behavior it's tested against. That work was done in anticipation of this
  step; don't restate the rationale here, update it there.
- Scope: infrastructure/deployment only (pooler sits in front of the single
  Postgres instance). Retune `pool_size`/`max_overflow` down once the
  pooler — not each backend process — owns the real connection budget.

### Shard by workspace_id — prefer connection-level routing; only touch `rows`' schema if that's insufficient

A workspace is the natural shard unit: every workspace member's data
co-locates, and workspace is already the authorization boundary. There are
two ways to implement that, with very different costs. Pick the first
unless a concrete need forces the second.

**Option A (preferred): route whole workspaces to physical Postgres
instances; change nothing in schema/RLS.** If one workspace's entire data
(`tables`, `rows`, `table_views`, `blob_objects`, `workspace_members`) lives
on a single physical Postgres instance, sharding is purely a connection-layer
concern: a small `workspace_id -> shard endpoint` directory (not itself
sharded — globally replicated or control-plane-held) resolved once per
request, from the `workspace_id`/`table_id` every request already carries in
its URL. Nothing on that shard changes: `rows.table_id -> tables.workspace_id`
is still a **local** join once routed, so V71's fix (no redundant,
driftable `workspace_id` on children) is untouched and stays correct. No
RLS policy, trigger, or schema change is needed. This is the default plan.

**Option B (only if a single workspace outgrows one Postgres instance):**
hash-distribute at the row level within one cluster using something like
Citus. This requires `workspace_id` to physically exist as a column on
`rows` (and other candidate children — `table_views`, `blob_objects`),
because Citus's distribution/colocation mechanism hashes on a real column
on the table being distributed; it cannot route by joining to `tables`
first. Only adopt this path, and only then:
- **This intentionally re-admits the exact duplication V71 removed**
  ("V71 removed child `workspace_id`: duplicating it allowed a child to
  claim a workspace different from its parent table" — `llm.core.md`). V71's
  fix must survive the reintroduction: `workspace_id` can come back only if
  it is guaranteed consistent with the parent table's `workspace_id` by
  construction — e.g. a trigger or generated value sourced from
  `tables.workspace_id` at insert time — never a caller-supplied or
  independently-writable column. Reintroducing it as a plain writable
  column without that guarantee reopens the exact bug V71 fixed.
- Do not do this pre-emptively, and do not do it at all unless Option A is
  provably insufficient (i.e. a single workspace's data must itself be
  split across nodes). It is schema + RLS policy + trigger work that
  reopens a closed correctness question for no benefit if Option A would
  have covered the actual scaling need.

## Column types are storage only, and indexes are on demand (0.94.0)

Every table's rows live in one physical `rows` table and the user picks each
column's type at run time, so the platform cannot know which columns will be
queried, and an index nobody uses still taxes every write of every table.

- The storage types are `text`, `int`, `double`, `strings`, `blob`. A date, a
  link, a select, tags and a checkbox are readings of those, chosen by the
  client in `options.display`. The server never reads it.
- Converting an old column depends on its data and meaning, so no migration
  does it; an operator or an LLM converts one column at a time.
- A blank table has no columns; only a template seeds a starter set.
- No index is created automatically. On request: btree for `text` and `int`,
  GIN for `strings`. `double` is refused by product rule. PostgreSQL decides.
- Indexes of deleted tables are reclaimed out of band
  (`drop_orphan_row_indexes`): `DROP INDEX` locks the shared `rows` table.
- Open: no query is shown to use a per-column index, and `CREATE`/`DROP INDEX`
  runs inside the request, not `CONCURRENTLY`, blocking writes to `rows`.
