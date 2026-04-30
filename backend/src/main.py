# src/main.py

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.redis import close_redis, get_redis
from config.settings import settings
from config.storage import ensure_bucket_exists
from core.db import close_db, init_db
from middleware.jwks import get_jwks
from router.api.admin.users import router as admin_users_router
from router.api.auth import router as api_auth_router
from router.api.dashboard import router as api_dashboard_router
from router.api.rows import router as api_rows_router
from router.api.storage import router as api_storage_router
from router.api.tables import router as api_tables_router
from router.api.workspaces import router as api_workspaces_router

# Local imports
from ServerTee import ServerTee

# --------------------------------------------------
# Logging setup
# --------------------------------------------------

today_date = datetime.now().strftime("%Y-%m-%d")
os.makedirs("log", exist_ok=True)
log_file_path = f"log/{today_date}.log"

tee = ServerTee(log_file_path)
print(f"📝 Logging to: {log_file_path}")


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

    # Initialize Valkey
    try:
        redis = await get_redis()
        await redis.ping()
        print("✓ Valkey connected")
    except Exception as e:
        print(f"⚠ Valkey connection failed: {e}")

    # Pre-warm JWKS cache
    try:
        await get_jwks()
        print("✓ JWKS pre-cached in Valkey")
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
    await close_redis()
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
Lattice Cast backend API for project management.

## Authentication
- **Google OAuth**: Exchange auth code at `/api/login/google/token`
- **Authentik OAuth**: JWT validation with JWKS

## Features
- User management (admin)
- Health monitoring
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
api_router.include_router(api_storage_router)
api_router.include_router(admin_users_router)
api_router.include_router(api_workspaces_router)
api_router.include_router(api_tables_router)
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
    valkey: str
    db: str


@api_router.get("/status", response_model=StatusResponse, tags=["health"])
async def status() -> StatusResponse:
    # Check Valkey
    valkey_status = "ok"
    try:
        valkey = await get_redis()
        await valkey.ping()
    except Exception as e:
        valkey_status = f"error: {str(e)}"

    return StatusResponse(
        status="ok",
        valkey=valkey_status,
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
    valkey_url: str
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
        valkey_url=settings.redis.url.split("@")[-1] if "@" in settings.redis.url else settings.redis.url,
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
        port=settings.backend_port,
        reload=True,
    )
