# LLM Context - Storage System

> **Note:** For general project context, see `llm.md`.

S3-compatible object storage using MinIO for user data persistence (activity history, preferences, etc.).

## Architecture

```
Frontend (storage.ts) → Backend (router/api/storage.py) → MinIO (:9000)
```

## Backend

### Files
- `config/storage.py` - S3 client singleton (boto3)
- `router/api/storage.py` - REST API endpoints

### Path Isolation
- **Admin**: Full access to all paths
- **User**: Files prefixed with UUID (first 20 chars, no dashes)
  - User sees `/file.txt` → stored as `{uuid_prefix}/file.txt`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/storage/files` | List files (with prefix filter) |
| GET | `/api/storage/file/{path}` | Download file |
| PUT | `/api/storage/file/{path}` | Upload file |
| DELETE | `/api/storage/file/{path}` | Delete file |
| GET | `/api/storage/admin/files` | Admin: list all files |

### Request/Response

```python
# List files
GET /api/storage/files?prefix=&max_keys=1000
→ { files: [{key, size, last_modified}], prefix, truncated }

# Upload (multipart/form-data)
PUT /api/storage/file/entries.json
← { key: "entries.json", size: 1234 }

# Download
GET /api/storage/file/entries.json
← StreamingResponse (file content)
```

## Frontend

### Files
- `lib/backend/config.ts` - `BACKEND_URL`
- `lib/backend/storage.ts` - Storage API client

### Usage

```typescript
import { loadJson, saveJson } from '$lib/backend/storage';

// Load JSON data
const data = await loadJson<MyType>('data.json');

// Save JSON data
await saveJson('data.json', { key: 'value' });
```

### Functions

```typescript
// Load JSON from storage (returns null if not found)
async function loadJson<T>(path: string): Promise<T | null>

// Save JSON to storage (returns success boolean)
async function saveJson<T>(path: string, data: T): Promise<boolean>
```

## Environment

```bash
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=lattice-cast
MINIO_SECURE=false
```
