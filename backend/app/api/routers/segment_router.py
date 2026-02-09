"""
Routes de segmentation, meteo, features derivees et training load.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
from datetime import date as date_type, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select, func
from typing import List, Optional
from uuid import UUID

from app.core.database import get_session
from app.auth.jwt import get_current_user_id
from app.domain.entities.activity import Activity
from app.domain.entities.segment import Segment, SegmentRead
from app.domain.entities.segment_features import SegmentFeatures, SegmentFeaturesRead
from app.domain.entities.activity_weather import ActivityWeather, ActivityWeatherRead
from app.domain.entities.training_load import TrainingLoad, TrainingLoadRead
from app.domain.services import segmentation_service
from app.domain.services import weather_service
from app.domain.services import derived_features_service
from app.api.routers._shared import security, resolve_activity

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/segments/process")
async def process_all_segments(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Segmente toutes les activites enrichies de l'utilisateur."""
    user_id = get_current_user_id(token.credentials)
    try:
        result = segmentation_service.segment_all_enriched(session, user_id)
        return result
    except Exception as e:
        logger.error(f"Erreur segmentation globale user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la segmentation: {str(e)}",
        )


@router.post("/segments/process/{activity_id}")
async def process_activity_segments(
    activity_id: str,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Segmente une activite specifique (accepte UUID ou strava_id)."""
    user_id = get_current_user_id(token.credentials)

    activity = resolve_activity(session, activity_id, user_id)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activite non trouvee",
        )

    try:
        count = segmentation_service.segment_activity(session, activity)
        return {"activity_id": str(activity.id), "segments_created": count}
    except Exception as e:
        logger.error(f"Erreur segmentation activite {activity_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la segmentation: {str(e)}",
        )


@router.get("/segments/status")
async def get_segmentation_status(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Retourne le statut de segmentation pour l'utilisateur."""
    user_id = get_current_user_id(token.credentials)

    total_activities = session.exec(
        select(func.count(Activity.id)).where(Activity.user_id == user_id)
    ).one()

    enriched_activities = session.exec(
        select(func.count(Activity.id)).where(
            Activity.user_id == user_id,
            Activity.streams_data.is_not(None),
        )
    ).one()

    segmented_activities = session.exec(
        select(func.count(func.distinct(Segment.activity_id))).where(
            Segment.user_id == user_id
        )
    ).one()

    total_segments = session.exec(
        select(func.count(Segment.id)).where(Segment.user_id == user_id)
    ).one()

    return {
        "total_activities": total_activities,
        "enriched_activities": enriched_activities,
        "segmented_activities": segmented_activities,
        "pending_segmentation": enriched_activities - segmented_activities,
        "total_segments": total_segments,
    }


@router.get("/segments/{activity_id}")
async def get_activity_segments(
    activity_id: str,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Retourne les segments d'une activite avec leurs features (accepte UUID ou strava_id)."""
    user_id = get_current_user_id(token.credentials)

    activity = resolve_activity(session, activity_id, user_id)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activite non trouvee",
        )

    segments = session.exec(
        select(Segment)
        .where(Segment.activity_id == activity.id)
        .order_by(Segment.segment_index)
    ).all()

    # Recuperer les features pour chaque segment
    result = []
    for seg in segments:
        features = session.exec(
            select(SegmentFeatures).where(SegmentFeatures.segment_id == seg.id)
        ).first()

        result.append({
            "segment": SegmentRead.model_validate(seg),
            "features": SegmentFeaturesRead.model_validate(features) if features else None,
        })

    return {
        "activity_id": str(activity.id),
        "segment_count": len(result),
        "segments": result,
    }


# ──────────────────────────────────────────────
# Routes meteo (tache 2.3.1)
# ──────────────────────────────────────────────


@router.get("/weather/{activity_id}")
async def get_activity_weather(
    activity_id: str,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Retourne les donnees meteo d'une activite (accepte UUID ou strava_id)."""
    user_id = get_current_user_id(token.credentials)

    activity = resolve_activity(session, activity_id, user_id)
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activite non trouvee",
        )

    weather = session.exec(
        select(ActivityWeather).where(ActivityWeather.activity_id == activity.id)
    ).first()
    if not weather:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Donnees meteo non disponibles pour cette activite",
        )

    return ActivityWeatherRead.model_validate(weather)


@router.post("/weather/enrich")
async def enrich_all_activities_weather(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Enrichit toutes les activites de l'utilisateur avec les donnees meteo."""
    user_id = get_current_user_id(token.credentials)
    try:
        result = await weather_service.enrich_all_weather(session, user_id)
        return result
    except Exception as e:
        logger.error(f"Erreur enrichissement meteo user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'enrichissement meteo: {str(e)}",
        )


@router.get("/weather/status")
async def get_weather_status(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Retourne le statut d'enrichissement meteo pour l'utilisateur."""
    user_id = get_current_user_id(token.credentials)

    total_activities = session.exec(
        select(func.count(Activity.id)).where(Activity.user_id == user_id)
    ).one()

    with_streams = session.exec(
        select(func.count(Activity.id)).where(
            Activity.user_id == user_id,
            Activity.streams_data.is_not(None),
        )
    ).one()

    with_weather = session.exec(
        select(func.count(ActivityWeather.id)).where(
            ActivityWeather.activity_id.in_(
                select(Activity.id).where(Activity.user_id == user_id)
            )
        )
    ).one()

    return {
        "total_activities": total_activities,
        "with_streams": with_streams,
        "with_weather": with_weather,
        "pending_weather": with_streams - with_weather,
    }


# ──────────────────────────────────────────────
# Routes features derivees (tache 4.4.1)
# ──────────────────────────────────────────────


@router.post("/features/compute")
async def compute_all_features(
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Calcule les features derivees per-segment pour toutes les activites de l'utilisateur."""
    user_id = get_current_user_id(token.credentials)
    try:
        result = derived_features_service.compute_all_segment_features(session, user_id)
        return result
    except Exception as e:
        logger.error(f"Erreur features derivees user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul des features: {str(e)}",
        )


@router.post("/features/compute/{activity_id}")
async def compute_activity_features(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Calcule les features derivees per-segment pour une activite specifique."""
    user_id = get_current_user_id(token.credentials)

    activity = session.exec(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == user_id,
        )
    ).first()
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activite non trouvee",
        )

    try:
        count = derived_features_service.compute_segment_features(session, activity_id)
        return {"activity_id": str(activity_id), "segments_updated": count}
    except Exception as e:
        logger.error(f"Erreur features derivees activite {activity_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul des features: {str(e)}",
        )


# ──────────────────────────────────────────────
# Routes training load (tache 4.4.1)
# ──────────────────────────────────────────────


@router.get("/training-load")
async def get_training_load(
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Retourne les donnees de training load pour l'utilisateur sur une plage de dates."""
    user_id = get_current_user_id(token.credentials)

    query = select(TrainingLoad).where(TrainingLoad.user_id == user_id)
    if date_from:
        query = query.where(TrainingLoad.date >= date_from)
    if date_to:
        query = query.where(TrainingLoad.date <= date_to)
    query = query.order_by(TrainingLoad.date)

    rows = session.exec(query).all()
    return [TrainingLoadRead.model_validate(r) for r in rows]


@router.post("/training-load/compute")
async def compute_training_load(
    date_from: Optional[date_type] = Query(None),
    date_to: Optional[date_type] = Query(None),
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Calcule CTL/ATL/TSB pour l'utilisateur. Defaut : 90 derniers jours jusqu'a aujourd'hui."""
    user_id = get_current_user_id(token.credentials)

    today = date_type.today()
    d_from = date_from or (today - timedelta(days=90))
    d_to = date_to or today

    try:
        days = derived_features_service.compute_training_load(session, user_id, d_from, d_to)
        return {"days_computed": days, "date_from": str(d_from), "date_to": str(d_to)}
    except Exception as e:
        logger.error(f"Erreur training load user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du calcul du training load: {str(e)}",
        )
