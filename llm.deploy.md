# LLM Context - Deployment

> **Note:** For general project context, see `llm.md`.

## Quick Start (Development)

```bash
# All services
docker compose up

# Frontend only
cd frontend && npm run dev

# Backend only
cd backend && uvicorn src.main:app --reload --port 5000

# Run tests
docker compose --profile test run --rm backend-test
```

## Ports

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | SvelteKit dev server |
| Backend | 5000 | FastAPI server |
| PostgreSQL | 5432 (15432 external) | Database |
| Valkey | 6379 | Cache |
| MinIO | 9000, 9001 | S3 storage + console |

## Docker Compose

### Services

```yaml
frontend   # SvelteKit + Vite dev server
backend    # FastAPI + Uvicorn
db         # PostgreSQL 18
valkey     # Valkey 8 (alpine)
minio      # MinIO S3 storage
```

### Profiles

```bash
# Browser testing (Playwright)
docker compose --profile browser up -d browser
docker compose exec browser python browse.py status
docker compose exec browser python browse.py screenshot test
```

### Networks

- `app-network` - Internal services (backend, db, valkey, minio)
- `shared-network` - External network for cross-compose communication

### Volumes

- `db_data` - PostgreSQL data
- `valkey_data` - Valkey persistence
- `minio_data` - MinIO object storage

## Kubernetes (Production)

### Directory Structure

```
k8s/
├── namespace/
│   └── lattice-cast.yaml
├── secrets/
│   ├── postgres-secret.yaml
│   ├── minio-secret.yaml
│   └── oauth-secret.yaml
├── configmaps/
│   └── backend-config.yaml
├── *-deployment.yaml
├── *-service.yaml
└── *-ingress.yaml
```

### Deployment Order

```bash
# 1. Create namespace
kubectl apply -f namespace/lattice-cast.yaml

# 2. Apply secrets and configmaps
kubectl apply -f secrets/
kubectl apply -f configmaps/

# 3. Create TLS secret for HTTPS
kubectl create secret tls lattice-cast-tls-secret \
  --key yourdomain.com.key \
  --cert yourdomain.com.pem \
  -n lattice-cast

# 4. Deploy all services
kubectl apply -f .
```

### Build & Push to Registry

```bash
# Build images (source .env for build args)
set -a && source .env && set +a && docker compose build

# Tag and push frontend
docker tag lattice-cast-frontend:latest 127.0.0.1:7000/lattice-cast-frontend:latest
docker push 127.0.0.1:7000/lattice-cast-frontend:latest

# Tag and push backend
docker tag lattice-cast-backend:latest 127.0.0.1:7000/lattice-cast-backend:latest
docker push 127.0.0.1:7000/lattice-cast-backend:latest
```

> **Note:** Frontend build requires env vars (GOOGLE_CLIENT_ID, AUTHENTIK_*) to be exported before `docker compose build` because Vite bakes them into static files at build time.

### Debug & Restart

```bash
# Restart deployments
kubectl rollout restart deployment/frontend-deployment -n lattice-cast
kubectl rollout restart deployment/backend-deployment -n lattice-cast

# Port forward for local testing
kubectl port-forward service/frontend-service 3000:3000 -n lattice-cast
kubectl port-forward service/backend-service 5000:5000 -n lattice-cast

# View logs
kubectl logs -f deployment/frontend-deployment -n lattice-cast
kubectl logs -f deployment/backend-deployment -n lattice-cast
```

### Ingress Routing

| Path | Service | Notes |
|------|---------|-------|
| `/` | frontend | Static files (SvelteKit) |
| `/api/*` | backend | API endpoints |

### HTTPS Setup

Add domain to `vite.config.ts`:
```javascript
allowedHosts: [
    'localhost',
    '127.0.0.1',
    'lattice-cast.posetmage.com',
],
```

## Environment Variables

Copy from example:
```bash
cp .env.example .env
```

Key variables:

| Variable | Description |
|----------|-------------|
| `POSTGRES_USER/PASSWORD/DB` | Database credentials |
| `MINIO_*` | MinIO storage config |
| `GOOGLE_CLIENT_ID/SECRET` | Google OAuth (build-time for frontend) |
| `AUTHENTIK_*` | Authentik OAuth (build-time for frontend) |

> **Important:** OAuth variables must be available at build time for frontend. The `docker-compose.yml` passes them as build args to `frontend/Dockerfile`.
