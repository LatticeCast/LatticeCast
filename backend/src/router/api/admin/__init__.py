# router/api/admin/__init__.py
"""Every admin-only endpoint lives under /api/v1/admin and is guarded here, once.

`require_admin` is applied to this parent router, so a sub-router cannot forget
it and no endpoint outside /admin may use it (tests/test_admin_routes.py).
Sub-routers carry no admin check of their own.
"""

from fastapi import APIRouter, Depends

from middleware.auth import require_admin
from router.api.admin.announcements import router as announcements_router
from router.api.admin.sso import router as sso_router
from router.api.admin.storage import router as storage_router
from router.api.admin.users import router as users_router

router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])
router.include_router(users_router)
router.include_router(announcements_router)
router.include_router(sso_router)
router.include_router(storage_router)
