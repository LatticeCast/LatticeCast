"""Tables API router — pure composition.

Each sub-module declares its own `prefix="/tables"` and registers the
routes that belong to its domain. We just wire them together here so
the only place to look for endpoint code is the matching sub-module:

    crud.py      — list / create / get / update / delete on a single table
    templates.py — POST /tables/template/{pm,crm}
    columns.py   — column CRUD under /tables/{id}/columns
    views.py     — view CRUD + view-order + default-view under /tables/{id}/
"""

from fastapi import APIRouter

from .columns import router as columns_router
from .crud import router as crud_router
from .templates import router as templates_router
from .views import router as views_router

router = APIRouter()

router.include_router(crud_router)
router.include_router(templates_router)
router.include_router(columns_router)
router.include_router(views_router)
