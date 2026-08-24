# src/main.py

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import settings
from config.storage import ensure_bucket_exists
from core.db import close_db, init_db
from middleware.jwks import get_jwks
from router.api.admin.announcements import router as admin_announcements_router
from router.api.admin.users import router as admin_users_router
from router.api.announcements import router as api_announcements_router
from router.api.auth import router as api_auth_router
from router.api.dashboard import router as api_dashboard_router
from router.api.rows import router as api_rows_router
from router.api.storage import router as api_storage_router
from router.api.table_schemas import router as api_table_schemas_router
from router.api.tables import router as api_tables_router
from router.api.workspaces import router as api_workspaces_router

# --------------------------------------------------
# Lifespan (Startup / Shutdown)
# --------------------------------------------------

executor = ThreadPoolExecutor(max_workers=5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting up services...")

    # Initialize database
    await init_db()
    print("✓ Database initialized")

    # Pre-warm JWKS cache
    try:
        await get_jwks()
        print("✓ JWKS pre-cached")
    except Exception as e:
        print(f"⚠ JWKS pre-cache failed: {e}")

    # Initialize MinIO bucket
    try:
        await ensure_bucket_exists()
        print("✓ MinIO storage ready")
    except Exception as e:
        print(f"⚠ MinIO initialization failed: {e}")

    yield

    # Shutdown
    print("🛑 Shutting down services...")
    executor.shutdown(wait=True)
    await close_db()
    print("✓ Shutdown complete")


# --------------------------------------------------
# FastAPI initialization
# --------------------------------------------------

app = FastAPI(
    title="Lattice Cast API",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    description="""
Generic workspace/table API. PM, CRM, and workflow features are table schemas and views on the same primitives.

## Use the API
1. Authenticate and send `Authorization: Bearer <token>`.
2. Create or resolve a workspace, then create/read a table. A `table_id` may exist in more than one workspace; pass `workspace_id` when ambiguity is possible.
3. Read the table schema. Row values are keyed by the returned column UUID, never by the column name.
4. After any table/schema/view mutation, replace local schema state with the returned full schema snapshot.

## Blob cells
A `blob` column holds exactly one object. Its `options.kind` is a picker/rendering hint:

| kind | intended content | write route |
| --- | --- | --- |
| `file` | any file or binary (ZIP, PDF, etc.) | generic blob upload |
| `image` | image file | generic blob upload |
| `table` | CSV, XLSX, JSONL | generic blob upload |
| `doc` | Markdown text | doc blob route |

`accept` is a browser file-picker hint; the generic blob API stores one arbitrary uploaded file and preserves its MIME type. Blob metadata is returned in `row_data[column_id]`; bodies are downloaded from the addressed blob endpoint.

Use the **rows** tag for the exact upload, download, document, and delete contracts. Legacy `/doc` and `/col-doc` routes remain for compatibility; new clients should use addressed blob routes.
    """,
    version="1.0.0",
    contact={
        "name": "Lattice Cast Team",
        "url": "https://lattice-cast.posetmage.com",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=[
        {"name": "auth", "description": "Authentication endpoints (Google/Authentik OAuth)"},
        {"name": "workspaces", "description": "Workspace lifecycle and RLS-backed member access."},
        {"name": "tables", "description": "Generic table, column, schema, template, and view operations."},
        {
            "name": "rows",
            "description": "Row CRUD plus one-file blob cells. Read the blob endpoint descriptions before integrating uploads.",
        },
        {"name": "dashboard", "description": "Dashboard block queries over table rows."},
        {"name": "storage", "description": "File storage (S3-compatible, user files prefixed with UUID)"},
        {"name": "admin-users", "description": "User management (requires admin role)"},
        {"name": "health", "description": "Health check and debug endpoints"},
    ],
    lifespan=lifespan,
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Parent API router - all routes under /api
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(api_auth_router)
api_router.include_router(api_announcements_router)
api_router.include_router(api_storage_router)
api_router.include_router(admin_announcements_router)
api_router.include_router(admin_users_router)
api_router.include_router(api_workspaces_router)
api_router.include_router(api_tables_router)
api_router.include_router(api_table_schemas_router)
api_router.include_router(api_dashboard_router)
api_router.include_router(api_rows_router)


# --------------------------------------------------
# Thread pool for blocking tasks
# --------------------------------------------------


def blocking_task(seconds: int):
    print(f"⏳ Start blocking task for {seconds} seconds")
    time.sleep(seconds)
    return f"Task finished after {seconds} seconds"


@api_router.get("/run-task/{seconds}", tags=["health"])
async def run_task(seconds: int):
    """Execute a blocking task for testing thread pool (debug only)"""
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(executor, blocking_task, seconds)
    return {"result": result}


# --------------------------------------------------
# Health check
# --------------------------------------------------


class StatusResponse(BaseModel):
    status: str
    db: str


@api_router.get("/status", response_model=StatusResponse, tags=["health"])
async def status() -> StatusResponse:
    return StatusResponse(
        status="ok",
        db="ok",  # DB is checked via healthcheck
    )


# --------------------------------------------------
# OpenAPI export
# --------------------------------------------------


def export_openapi_spec(output_path: str = "openapi.json") -> str:
    """Export OpenAPI spec to a JSON file"""
    import json

    spec = app.openapi()
    with open(output_path, "w") as f:
        json.dump(spec, f, indent=2)
    return output_path


@api_router.get("/openapi-export", tags=["health"])
async def openapi_export():
    """Export OpenAPI spec to file and return path"""
    path = export_openapi_spec()
    return {"message": f"OpenAPI spec exported to {path}", "path": path}


class SettingsInfoResponse(BaseModel):
    """Non-sensitive settings information"""

    debug_mode: bool
    database_host: str
    minio_endpoint: str
    minio_bucket: str
    cors_origins: list[str]


@api_router.get("/settings", response_model=SettingsInfoResponse, tags=["health"])
async def get_settings_info() -> SettingsInfoResponse:
    """Get current settings (non-sensitive values only)"""
    db_host, _ = settings.database.url.split(":")
    return SettingsInfoResponse(
        debug_mode=settings.debug_mode,
        database_host=db_host,
        minio_endpoint=settings.minio.endpoint,
        minio_bucket=settings.minio.bucket,
        cors_origins=settings.cors_origins,
    )


# Include all API routes under /api prefix
app.include_router(api_router)


# --------------------------------------------------
# Local Entrypoint
# --------------------------------------------------

if __name__ == "__main__":
    import sys

    import uvicorn

    # CLI: python -m src.main --export-openapi [output.json]
    if "--export-openapi" in sys.argv:
        idx = sys.argv.index("--export-openapi")
        output_path = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else "openapi.json"
        export_openapi_spec(output_path)
        print(f"✓ OpenAPI spec exported to: {output_path}")
        sys.exit(0)

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.NGX_PORT,
        reload=True,
    )
