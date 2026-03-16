# LLM Context - Development Guide

> **Note:** For deployment to k8s, see `llm.deploy.md`. For general project context, see `llm.md`.

## Development Philosophy

- **Frontend**: Svelte 5 + Tailwind CSS 4, pure CSR (no SSR), static site build
- **Backend**: FastAPI, test with curl on localhost
- **K8s**: Only deploy when user explicitly requests

## Frontend Development

### Tech Stack
- Svelte 5 with runes (`$state`, `$derived`, `$effect`)
- Tailwind CSS 4 (use `bg-linear-to-r` not `bg-gradient-to-r`)
- Pure CSR - no SSR, no Node.js runtime needed
- Static site build for GitHub Pages hosting

### Static Site Config

```javascript
// svelte.config.js
import adapter from '@sveltejs/adapter-static';

export default {
  kit: {
    adapter: adapter({
      fallback: 'index.html'  // SPA fallback
    })
  }
};
```

### Development Workflow

```bash
# 1. Start services
docker compose up frontend -d

# 2. Make code changes...

# 3. Lint and verify
docker compose exec frontend npm run lint
docker compose exec frontend npm run build

# 4. If changes need restart
docker compose down
docker compose up frontend -d
```

### Svelte 5 Patterns

```svelte
<script lang="ts">
  // State (reactive)
  let count = $state(0);
  let items = $state<string[]>([]);

  // Derived (computed)
  const doubled = $derived(count * 2);

  // Effect (side effects)
  $effect(() => {
    console.log('count:', count);
  });

  // Props
  let { title } = $props<{ title: string }>();
</script>
```

### Tailwind CSS 4 Patterns

```svelte
<!-- Gradient (v4 syntax) -->
<div class="bg-linear-to-br from-violet-500 to-fuchsia-500">

<!-- Card -->
<div class="rounded-3xl bg-white p-8 shadow-2xl">

<!-- Button -->
<button class="rounded-2xl bg-linear-to-r from-violet-500 to-fuchsia-500 px-4 py-4 text-white">
```

## Backend Development

### Development Workflow

```bash
# 1. Start services
docker compose up backend -d

# 2. Make code changes...

# 3. Restart to apply changes
docker compose down
docker compose up backend -d

# 4. Test with curl
curl http://localhost:5000/api/status
```

### Testing Endpoints with curl

```bash
# Health check
curl http://localhost:5000/api/status

# Get settings
curl http://localhost:5000/api/settings

# Login (need OAuth flow first, then use token)
curl http://localhost:5000/api/login/me \
  -H "Authorization: Bearer $TOKEN"

# Storage - list files
curl http://localhost:5000/api/storage/files \
  -H "Authorization: Bearer $TOKEN"

# Admin - list users (admin token required)
curl http://localhost:5000/api/admin/users \
  -H "Authorization: Bearer $TOKEN"

# Admin - add user
curl -X POST http://localhost:5000/api/admin/users \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": "user@example.com", "role": "user"}'
```

### FastAPI Patterns

```python
from fastapi import APIRouter, Depends
from middleware.auth import get_current_user, require_admin
from models.user import User

router = APIRouter(prefix="/myroute", tags=["myroute"])

# Public endpoint
@router.get("/public")
async def public():
    return {"message": "hello"}

# Protected endpoint (any registered user)
@router.get("/protected")
async def protected(user: User = Depends(get_current_user)):
    return {"email": user.id}

# Admin only
@router.post("/admin-only")
async def admin_only(user: User = Depends(require_admin)):
    return {"admin": user.id}
```

## Frontend Debugging with Playwright

Use the browser container to test the frontend visually.

```bash
# Start browser service
docker compose --profile browser up -d browser

# Check page status
docker compose exec browser python browse.py status

# Take screenshot
docker compose exec browser python browse.py screenshot test_page

# List all buttons on page
docker compose exec browser python browse.py buttons

# Click element (by data-testid or text)
docker compose exec browser python browse.py click "login-google"
docker compose exec browser python browse.py click "Continue"

# Open menu
docker compose exec browser python browse.py menu
```

### Screenshots

Screenshots are saved to `.browser/` directory (git-ignored).

```bash
# View screenshot
ls -la .browser/
# Open with image viewer
```

### Custom Playwright Script

```bash
docker compose exec browser python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto('http://frontend:3000')
    print('Title:', page.title())
    page.screenshot(path='/output/custom.png')
    browser.close()
"
```

### Testing Production Site

```bash
# Test deployed site
docker compose exec browser python browse.py status https://lattice-cast.posetmage.com
docker compose exec browser python browse.py screenshot prod https://lattice-cast.posetmage.com
```

## Full Development Cycle

### Frontend Changes

```bash
# Edit frontend code...

# Verify
docker compose exec frontend npm run lint
docker compose exec frontend npm run build

# If errors, fix and retry
# If build passes, changes are ready
```

### Backend Changes

```bash
# Edit backend code...

# Restart
docker compose down
docker compose up backend -d

# Test
curl http://localhost:5000/api/status
curl http://localhost:5000/api/your-new-endpoint
```

### Both Frontend + Backend

```bash
# Start all
docker compose up -d

# Make changes...

# Verify frontend
docker compose exec frontend npm run lint
docker compose exec frontend npm run build

# Restart backend
docker compose restart backend

# Test backend
curl http://localhost:5000/api/status
```

## K8s Deployment

**Only do this when user explicitly requests k8s deployment.**

```bash
# Build with env vars
set -a && source .env && set +a && docker compose build

# Push to registry
docker tag lattice-cast-frontend:latest 127.0.0.1:7000/lattice-cast-frontend:latest
docker push 127.0.0.1:7000/lattice-cast-frontend:latest

docker tag lattice-cast-backend:latest 127.0.0.1:7000/lattice-cast-backend:latest
docker push 127.0.0.1:7000/lattice-cast-backend:latest

# Restart deployments
kubectl rollout restart deployment/frontend-deployment -n lattice-cast
kubectl rollout restart deployment/backend-deployment -n lattice-cast
```

## Common Issues

### Frontend not updating
```bash
docker compose down
docker compose up frontend -d
```

### Backend not reloading
```bash
docker compose restart backend
# or full restart
docker compose down
docker compose up backend -d
```

### Lint errors
```bash
docker compose exec frontend npm run lint
# Fix errors shown, then retry
```

### Build errors
```bash
docker compose exec frontend npm run build
# Check error output, fix code, retry
```

## API Routes Summary

All backend routes are under `/api`:

| Route | Description |
|-------|-------------|
| `/api/status` | Health check |
| `/api/settings` | Current settings |
| `/api/login/*` | OAuth endpoints |
| `/api/storage/*` | File storage |
| `/api/admin/users/*` | User management |
