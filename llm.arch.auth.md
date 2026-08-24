# Authentication

Bearer tokens may be local JWT, Google, or Authentik. Token verification resolves an existing `auth.users` identity; it does not create one.

```text
token -> middleware/token.py -> middleware/auth.py -> RLS session -> PostgreSQL policy
```

- Application role (`user`/`admin`) differs from workspace access (`read`/`write`/`owner`).
- Keep normal data routes on the RLS engine; use the manager engine only for login/admin flows.
- Password hashes stay in `gdpr.user_password`; never expose them through app-role reads.
