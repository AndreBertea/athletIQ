"""
Routes Garmin Connect : auth (login/status/disconnect), sync, daily data.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select
from uuid import UUID

from app.core.database import get_session
from app.auth.jwt import get_current_user_id
from app.domain.entities.garmin_daily import GarminDaily, GarminDailyRead
from app.domain.services.auth_service import auth_service
from app.domain.entities.fit_metrics import FitMetrics, FitMetricsRead
from app.domain.services.garmin_sync_service import (
    sync_daily_data,
    sync_garmin_activities,
    preview_garmin_activity_import,
    enrich_garmin_activity_fit,
    batch_enrich_garmin_fit,
    get_garmin_enrichment_status,
    get_garmin_period_import_status,
)
from app.domain.services.race_predictor.reference_detection_service import detect_reference_candidates
from app.domain.services.race_predictor.v3_residual_service import train_v3_residual_model
from app.api.routers._shared import security, limiter, resolve_activity

logger = logging.getLogger(__name__)

router = APIRouter()


def _detect_reference_candidates_after_garmin_update(session: Session, user_id: UUID) -> dict:
    """Refresh les candidats et entraine V3 sans bloquer le workflow Garmin."""
    try:
        candidates = detect_reference_candidates(session, user_id, limit=300)
        residual_model = train_v3_residual_model(
            session,
            user_id,
            force_detect=False,
        )
        return {
            "detected_count": len(candidates),
            "v3_residual_model": {
                "status": residual_model.status,
                "eligible_count": residual_model.eligible_count,
                "selected_count": residual_model.selected_count,
                "observation_count": residual_model.observation_count,
                "trained_at": residual_model.trained_at.isoformat()
                if residual_model.trained_at
                else None,
            },
        }
    except Exception as exc:  # pragma: no cover - garde-fou operationnel
        logger.warning("Refresh Race Predictor impossible apres sync Garmin: %s", exc)
        return {"detected_count": 0, "v3_residual_model": None, "error": str(exc)}


class GarminLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ============ AUTH GARMIN ============

@router.post("/auth/garmin/login")
@limiter.limit("5/hour")
async def garmin_login(
    request: Request,
    body: GarminLoginRequest,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Login Garmin one-time. Email/password ne sont JAMAIS stockes."""
    user_id = get_current_user_id(token.credentials)
    try:
        return auth_service.handle_garmin_login(session, user_id, body.email, body.password)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur login Garmin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la connexion Garmin",
        )


@router.get("/auth/garmin/status")
async def garmin_status(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Verifie le statut de la connexion Garmin."""
    user_id = get_current_user_id(token.credentials)
    return auth_service.get_garmin_status(session, user_id)


@router.post("/auth/garmin/verify")
async def verify_garmin_token(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Vérifie que le token Garmin est toujours valide."""
    user_id = get_current_user_id(token.credentials)
    try:
        result = auth_service.verify_garmin_token(session, user_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur verification token Garmin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la vérification du token Garmin",
        )


@router.delete("/auth/garmin/disconnect")
async def garmin_disconnect(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Deconnecte Garmin (supprime le token)."""
    user_id = get_current_user_id(token.credentials)
    try:
        return auth_service.disconnect_garmin(session, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ============ SYNC GARMIN ============

@router.post("/sync/garmin")
async def sync_garmin(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    days_back: int = Query(default=30, ge=1, le=730),
):
    """Synchronise les donnees quotidiennes Garmin."""
    user_id = get_current_user_id(token.credentials)
    try:
        result = await sync_daily_data(session, UUID(user_id), days_back)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur sync Garmin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur sync Garmin: {str(e)}",
        )


# ============ DONNEES GARMIN ============

@router.get("/garmin/daily", response_model=List[GarminDailyRead])
async def get_garmin_daily(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    date_from: Optional[date_type] = Query(default=None),
    date_to: Optional[date_type] = Query(default=None),
):
    """Recupere les donnees quotidiennes Garmin pour une periode."""
    user_id = get_current_user_id(token.credentials)

    query = select(GarminDaily).where(GarminDaily.user_id == UUID(user_id))

    if date_from:
        query = query.where(GarminDaily.date >= date_from)
    if date_to:
        query = query.where(GarminDaily.date <= date_to)

    query = query.order_by(GarminDaily.date.desc())

    results = session.exec(query).all()
    return results


# ============ ACTIVITES GARMIN ============

@router.get("/garmin/activities/import-preview")
async def garmin_activity_import_preview(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    days_back: int = Query(default=30, ge=1, le=730),
):
    """Compte les activites Garmin a importer sur la periode avant la sync."""
    user_id = get_current_user_id(token.credentials)
    try:
        return await preview_garmin_activity_import(session, UUID(user_id), days_back)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur preview import activites Garmin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur preview import Garmin: {str(e)}",
        )


@router.get("/garmin/activities/import-status")
async def garmin_activity_import_status(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    days_back: int = Query(default=30, ge=1, le=730),
):
    """Retourne les compteurs FIT/meteo pour les activites Garmin de la periode."""
    user_id = get_current_user_id(token.credentials)
    return get_garmin_period_import_status(session, UUID(user_id), days_back)


@router.post("/sync/garmin/activities")
async def sync_garmin_act(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    days_back: int = Query(default=30, ge=1, le=730),
):
    """Synchronise les activites Garmin dans la table Activity."""
    user_id = get_current_user_id(token.credentials)
    try:
        user_uuid = UUID(user_id)
        result = await sync_garmin_activities(session, user_uuid, days_back)
        result["reference_candidates"] = _detect_reference_candidates_after_garmin_update(
            session,
            user_uuid,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur sync activites Garmin: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur sync activites Garmin: {str(e)}",
        )


@router.get("/garmin/enrichment-status")
async def garmin_enrichment_status(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Retourne le statut d'enrichissement FIT des activites Garmin."""
    user_id = get_current_user_id(token.credentials)
    return get_garmin_enrichment_status(session, UUID(user_id))


@router.post("/garmin/activities/{activity_id}/enrich-fit")
async def enrich_garmin_fit(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Enrichit une activite Garmin avec son fichier FIT."""
    user_id = get_current_user_id(token.credentials)
    try:
        user_uuid = UUID(user_id)
        result = await enrich_garmin_activity_fit(session, user_uuid, activity_id)
        result["reference_candidates"] = _detect_reference_candidates_after_garmin_update(
            session,
            user_uuid,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur enrichissement FIT: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur enrichissement FIT: {str(e)}",
        )


@router.post("/garmin/activities/enrich-fit")
async def batch_enrich_fit(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    max_activities: int = Query(default=50, ge=1, le=200),
):
    """Enrichit en batch les activites Garmin sans streams_data."""
    user_id = get_current_user_id(token.credentials)
    try:
        user_uuid = UUID(user_id)
        result = await batch_enrich_garmin_fit(session, user_uuid, max_activities)
        result["reference_candidates"] = _detect_reference_candidates_after_garmin_update(
            session,
            user_uuid,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Erreur batch enrichissement FIT: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur batch enrichissement FIT: {str(e)}",
        )


@router.get("/garmin/activities/{activity_id}/fit-metrics", response_model=FitMetricsRead)
async def get_fit_metrics(
    activity_id: str,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Recupere les metriques FIT (Running Dynamics) d'une activite (accepte UUID ou strava_id)."""
    user_id = get_current_user_id(token.credentials)

    activity = resolve_activity(session, activity_id, user_id)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activite non trouvee",
        )

    fm = session.exec(
        select(FitMetrics).where(FitMetrics.activity_id == activity.id)
    ).first()
    if not fm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pas de metriques FIT pour cette activite",
        )

    return fm
