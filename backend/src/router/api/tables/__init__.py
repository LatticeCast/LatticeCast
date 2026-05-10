from fastapi import APIRouter

from .columns import router as columns_router
from .crud import router as crud_router
from .templates import router as templates_router
from .views import router as views_router

router = APIRouter(prefix="/tables", tags=["tables"])
router.include_router(templates_router)
router.include_router(crud_router)
router.include_router(columns_router)
router.include_router(views_router)
