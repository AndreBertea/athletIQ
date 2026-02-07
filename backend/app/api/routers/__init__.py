"""
Routers API pour AthlétIQ.

Ce module regroupe tous les sous-routers et expose un router principal
a inclure dans l'application FastAPI.
"""
from fastapi import APIRouter

from app.api.routers.auth_router import router as auth_router
from app.api.routers.activity_router import router as activity_router
from app.api.routers.plan_router import router as plan_router
from app.api.routers.sync_router import router as sync_router
from app.api.routers.data_router import router as data_router
from app.api.routers.segment_router import router as segment_router
from app.api.routers._shared import limiter

router = APIRouter()

router.include_router(auth_router)
router.include_router(activity_router)
router.include_router(plan_router)
router.include_router(sync_router)
router.include_router(data_router)
router.include_router(segment_router)

__all__ = ["router", "limiter"]
