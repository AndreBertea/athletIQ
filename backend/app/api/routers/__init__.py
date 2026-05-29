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
from app.api.routers.garmin_router import router as garmin_router
from app.api.routers.prediction_router import router as prediction_router
from app.api.routers.prediction_v2_2_router import router as prediction_v2_2_router
from app.api.routers.live_router import router as live_router
from app.api.routers.coach_athlete_router import router as coach_athlete_router
from app.api.routers.checkin_router import router as checkin_router
from app.api.routers.gpx_route_router import router as gpx_route_router
from app.api.routers._shared import limiter

router = APIRouter()

router.include_router(auth_router)
router.include_router(activity_router)
router.include_router(plan_router)
router.include_router(sync_router)
router.include_router(data_router)
router.include_router(segment_router)
router.include_router(garmin_router)
router.include_router(prediction_router)
router.include_router(prediction_v2_2_router)
router.include_router(live_router)
router.include_router(coach_athlete_router)
router.include_router(checkin_router)
router.include_router(gpx_route_router)

__all__ = ["router", "limiter"]
