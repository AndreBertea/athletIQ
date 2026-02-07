"""
Routes des activites : CRUD, enrichissement, streams, type update.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Form
from fastapi.responses import JSONResponse
from sqlmodel import Session
from typing import Optional
from uuid import UUID

from app.core.database import get_session
from app.auth.jwt import get_current_user_id
from app.domain.entities import ActivityWithStreams, ActivityStats
from app.domain.services.activity_service import activity_service
from app.domain.services.auto_enrichment_service import auto_enrichment_service
from app.api.routers._shared import security

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/activities")
async def get_activities(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    activity_type: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="Date minimale ISO (YYYY-MM-DD)")
):
    """Recupere les activites de l'utilisateur avec pagination"""
    user_id = get_current_user_id(token.credentials)
    return activity_service.get_activities_paginated(
        session, user_id, page, per_page, activity_type, date_from
    )


@router.get("/activities/stats", response_model=ActivityStats)
async def get_activity_stats(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    period_days: int = Query(default=30, ge=1, le=365)
):
    """Recupere les statistiques d'activites"""
    user_id = get_current_user_id(token.credentials)
    return activity_service.get_activity_stats(session, user_id, period_days)


@router.get("/activities/enrichment-status")
async def get_enrichment_status(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Recupere les statistiques d'enrichissement depuis PostgreSQL"""
    try:
        user_id = get_current_user_id(token.credentials)
        return activity_service.get_enrichment_status(session, user_id)
    except Exception as e:
        logger.error(f"Erreur enrichment-status: {e}")
        raise HTTPException(status_code=500, detail=f"Erreur calcul statut enrichissement: {str(e)}")


# ============ ENDPOINTS DONNEES ENRICHIES ============

@router.get("/activities/enriched")
async def get_enriched_activities(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    sport_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="Date minimale ISO (YYYY-MM-DD)")
):
    """Recupere les activites enrichies depuis PostgreSQL avec pagination"""
    try:
        user_id = get_current_user_id(token.credentials)
        return activity_service.get_enriched_activities_paginated(
            session, user_id, page, per_page, sport_type, date_from
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur recuperation activites enrichies: {str(e)}")


@router.get("/activities/enriched/stats")
async def get_enriched_activity_stats(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    period_days: int = Query(30, ge=1, le=365),
    sport_type: Optional[str] = Query(None)
):
    """Recupere les statistiques des activites depuis PostgreSQL"""
    try:
        user_id = get_current_user_id(token.credentials)
        return activity_service.get_enriched_activity_stats(
            session, user_id, period_days, sport_type
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul statistiques enrichies: {str(e)}")


@router.get("/activities/enriched/{activity_id}")
async def get_enriched_activity(
    activity_id: int,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Recupere une activite enrichie specifique par strava_id"""
    try:
        user_id = get_current_user_id(token.credentials)
        return activity_service.get_enriched_activity(session, user_id, activity_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur recuperation activite enrichie: {str(e)}")


@router.get("/activities/enriched/{activity_id}/streams")
async def get_enriched_activity_streams(
    activity_id: int,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Recupere les streams d'une activite enrichie depuis PostgreSQL"""
    try:
        user_id = get_current_user_id(token.credentials)
        return activity_service.get_enriched_activity_streams(session, user_id, activity_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur recuperation streams: {str(e)}")


@router.get("/activities/{activity_id}", response_model=ActivityWithStreams)
async def get_activity(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Recupere une activite avec ses donnees detaillees"""
    user_id = get_current_user_id(token.credentials)
    try:
        return activity_service.get_activity_by_id(session, user_id, activity_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")


@router.post("/activities/{activity_id}/enrich")
async def enrich_single_activity(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Enrichit une activite specifique avec ses donnees detaillees Strava"""
    user_id = get_current_user_id(token.credentials)
    try:
        return activity_service.enrich_single(session, user_id, activity_id)
    except ValueError as e:
        error_msg = str(e)
        if "non trouvee" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/activities/enrich-batch")
async def enrich_batch_activities(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    max_activities: int = Query(default=10, ge=1, le=50)
):
    """Enrichit un lot d'activites avec les donnees detaillees Strava"""
    user_id = get_current_user_id(token.credentials)
    try:
        return activity_service.enrich_batch(session, user_id, max_activities)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur enrichissement batch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'enrichissement: {str(e)}"
        )


@router.get("/activities/{activity_id}/streams")
async def get_activity_streams(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Recupere les donnees detaillees (streams) d'une activite"""
    user_id = get_current_user_id(token.credentials)
    try:
        return activity_service.get_activity_streams(session, user_id, activity_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/activities/auto-enrich/start")
async def start_auto_enrichment(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Demarre l'enrichissement automatique pour l'utilisateur"""
    user_id = get_current_user_id(token.credentials)
    return auto_enrichment_service.start_enrichment_for_user(user_id)


@router.post("/activities/{activity_id}/prioritize")
async def prioritize_activity_enrichment(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Met une activite en priorite haute pour l'enrichissement"""
    user_id = get_current_user_id(token.credentials)
    try:
        return activity_service.prioritize_activity(session, user_id, activity_id)
    except ValueError as e:
        error_msg = str(e)
        if "non trouvee" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)


@router.options("/activities/{activity_id}/type")
async def options_activity_type(activity_id: str):
    """Support pour les requetes CORS OPTIONS"""
    return JSONResponse(content={}, status_code=200)


@router.patch("/activities/{activity_id}/type")
async def update_activity_type(
    activity_id: str,
    activity_type: str = Form(...),
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Met a jour le type d'activite d'une activite"""
    user_id = get_current_user_id(token.credentials)
    try:
        return activity_service.update_activity_type(session, user_id, activity_id, activity_type)
    except ValueError as e:
        error_msg = str(e)
        if "non trouvee" in error_msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
