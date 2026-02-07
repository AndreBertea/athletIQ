"""
Routes de synchronisation : sync Strava, webhooks, queue d'enrichissement, quota.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.core.database import get_session
from app.auth.jwt import get_current_user_id
from app.domain.services.activity_service import activity_service
from app.domain.services.detailed_strava_service import detailed_strava_service
from app.domain.services.auto_enrichment_service import auto_enrichment_service
from app.api.routers._shared import security, limiter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync/strava")
async def sync_strava_activities(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    days_back: int = Query(default=30, ge=1, le=99999)
):
    """Synchronise les activites Strava de l'utilisateur puis lance l'enrichissement automatique"""
    user_id = get_current_user_id(token.credentials)
    try:
        return activity_service.sync_and_enrich(session, user_id, days_back)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


# ============ QUOTA STRAVA ============

@router.get("/strava/quota")
async def get_strava_quota_status(
    token: str = Depends(security)
):
    """Recupere le statut des quotas API Strava"""
    get_current_user_id(token.credentials)
    return detailed_strava_service.quota_manager.get_status()


# ============ WEBHOOKS STRAVA ============

@router.get("/webhooks/strava")
@limiter.exempt
async def strava_webhook_validation(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    """Validation du challenge Strava pour la subscription webhook."""
    from app.domain.services.strava_webhook_handler import validate_webhook_challenge
    try:
        result = validate_webhook_challenge(hub_verify_token, hub_challenge)
        return JSONResponse(status_code=200, content=result)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/webhooks/strava")
@limiter.exempt
async def strava_webhook_event(request: Request):
    """Recoit les evenements webhook de Strava."""
    from app.domain.services.strava_webhook_handler import validate_and_dispatch_event, process_webhook_event
    try:
        event = await request.json()
    except Exception as e:
        logger.error(f"Webhook Strava: payload invalide: {e}")
        return JSONResponse(status_code=200, content={"status": "error", "detail": "invalid payload"})

    try:
        result = validate_and_dispatch_event(event)
    except ValueError as e:
        return JSONResponse(status_code=200, content={"status": "error", "detail": str(e)})

    asyncio.get_event_loop().run_in_executor(None, process_webhook_event, event)
    return JSONResponse(status_code=200, content=result)


# ============ ENRICHISSEMENT QUEUE ============

@router.get("/enrichment/queue-status")
async def get_enrichment_queue_status(
    token: str = Depends(security)
):
    """Recupere le statut de la queue d'enrichissement"""
    get_current_user_id(token.credentials)
    return auto_enrichment_service.get_queue_status()


@router.get("/enrichment/queue-position")
async def get_enrichment_queue_position(
    token: str = Depends(security)
):
    """Retourne la position de l'utilisateur courant dans la queue d'enrichissement"""
    user_id = get_current_user_id(token.credentials)
    return auto_enrichment_service.get_user_queue_position_with_status(user_id)
