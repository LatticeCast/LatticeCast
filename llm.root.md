# LLM Context - Lattice Cast

## Project Overview

Airtable-like project management system with flexible, user-defined schemas. All row data stored as PostgreSQL JSONB with GIN indexes.

**Domain:** `lattice-cast.posetmage.com`

> **Documentation:**
> - `llm.dev.md` - Development guide (local workflow, curl testing)
> - `llm.frontend.md` - Frontend (Svelte 5, Tailwind CSS 4, Playwright)
> - `llm.arch.auth.md` - Authentication architecture (OAuth, JWT, PKCE, middleware)
> - `llm.endpoint.md` - API endpoints reference
> - `llm.storage.md` - Storage system (MinIO, user files)
> - `llm.user.md` - User management (login API, admin API)
> - `llm.deploy.md` - Docker Compose, Kubernetes deployment

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | SvelteKit 2.x, Svelte 5, Tailwind CSS 4, TypeScript, Vite 7 |
| Backend | FastAPI, Python 3.12, Uvicorn |
| Database | PostgreSQL 18, SQLModel/SQLAlchemy async, JSONB + GIN |
| Cache | Valkey 8 (alpine) |
| Storage | MinIO (S3-compatible), boto3 |
| Auth | Google OAuth, Authentik |
| Containers | Docker Compose (dev), Kubernetes (prod) |

## Architecture

```mermaid
graph LR
    FE[Frontend<br>SvelteKit :3000] --> BE[Backend<br>FastAPI :5000]
    BE --> DB[(PostgreSQL<br>:5432)]
    BE --> RD[(Valkey<br>:6379)]
    BE --> MN[(MinIO<br>:9000)]
```

## Directory Structure

**Note:** Backend uses flat imports without `__init__.py` files.

```
lattice-cast/
├── backend/                  # Git submodule - FastAPI + Python 3.12
│   └── src/
│       ├── main.py           # App entry, routers, lifespan
│       ├── core/             # db.py (async engine, migrations)
│       ├── config/           # settings.py, redis.py, storage.py
│       ├── middleware/       # auth.py, token.py, jwks.py
│       ├── models/           # SQLModel schemas (user, table, column, row)
│       ├── repository/       # CRUD operations (user, table, column, row)
│       ├── router/api/       # auth.py, storage.py, tables.py, columns.py, rows.py
│       ├── router/api/admin/ # users.py
│       ├── util/             # security.py, logger.py
│       └── log/              # Auto-created daily log files
│
├── frontend/                 # Git submodule - SvelteKit + Tailwind CSS
│   └── src/
│       ├── routes/           # +page.svelte, login/, tables/, tables/[id]/, etc.
│       └── lib/
│           ├── auth/         # OAuth, PKCE implementation
│           ├── stores/       # Svelte stores (auth, settings, tables)
│           ├── backend/      # Backend API clients (auth, tables, storage)
│           ├── components/   # Table components (grid, toolbar, modals)
│           ├── types/        # TypeScript interfaces (auth, table, json)
│           └── UI/           # Button, Input, Label components
│
├── migration/                # *.sql files for DB schema (source of truth)
├── k8s/                      # Kubernetes manifests
├── browser/                  # Playwright browser automation
├── docker-compose.yml
├── llm.root.md               # This file
├── llm.dev.md                # Development guide
├── llm.frontend.md           # Frontend documentation
├── llm.arch.auth.md          # Auth architecture
├── llm.endpoint.md           # API endpoints documentation
├── llm.storage.md            # Storage system documentation
├── llm.user.md               # User management (login, admin)
├── llm.deploy.md             # Deployment documentation
└── .env
```

## Database Schema

### users
```sql
user_id     VARCHAR PRIMARY KEY  -- email address
name        VARCHAR NOT NULL DEFAULT ''
role        VARCHAR NOT NULL DEFAULT 'user'  -- 'user' | 'admin'
created_at  TIMESTAMP DEFAULT NOW()
updated_at  TIMESTAMP DEFAULT NOW()
```

### tables
```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
user_id     VARCHAR NOT NULL REFERENCES users(user_id)
name        VARCHAR NOT NULL
created_at  TIMESTAMP DEFAULT NOW()
updated_at  TIMESTAMP DEFAULT NOW()
```

### columns
```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
table_id    UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE
name        VARCHAR NOT NULL
type        VARCHAR NOT NULL  -- text, number, date, select, checkbox, url
options     JSONB NOT NULL DEFAULT '{}'
position    INTEGER NOT NULL DEFAULT 0
created_at  TIMESTAMP DEFAULT NOW()
```

### rows
```sql
id          UUID PRIMARY KEY DEFAULT gen_random_uuid()
table_id    UUID NOT NULL REFERENCES tables(id) ON DELETE CASCADE
data        JSONB NOT NULL DEFAULT '{}'  -- {"col_id": "value", ...}
created_at  TIMESTAMP DEFAULT NOW()
updated_at  TIMESTAMP DEFAULT NOW()

-- GIN index for fast JSONB queries
CREATE INDEX idx_rows_data ON rows USING GIN (data);
```

## Key Patterns

### Backend
- **Flat imports**: No `__init__.py` files
- **Pydantic Settings**: Centralized config in `config/settings.py`
- **SQL migrations**: Use `migration/*.sql`, not auto-create
- **Async everywhere**: asyncpg, httpx, redis-py
- **OpenAPI**: Auto-generated at `/docs`, `/redoc`
- **Repository pattern**: All DB operations in `repository/` layer
- **JSONB + GIN**: Flexible row data with fast filtering

### Frontend
See `llm.frontend.md` for details on Svelte 5, Tailwind CSS 4, and Playwright testing.

## Common Tasks

### Add new API endpoint
1. Create router in `backend/src/router/api/`
2. Add to `main.py` via `app.include_router()`
3. Use auth: `user: User = Depends(get_current_user)`

### Add new database table
1. Create `migration/*.sql` file
2. Define SQLModel in `models/`
3. Add repository in `repository/`
4. **Never use auto-create**

### Add new frontend route
See `llm.frontend.md` for Svelte 5 patterns and Playwright testing.
