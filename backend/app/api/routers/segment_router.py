"""
Routes de segmentation : traitement, consultation, statut.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select, func
from typing import List
from uuid import UUID

from app.core.database import get_session
from app.auth.jwt import get_current_user_id
from app.domain.entities.activity import Activity
from app.domain.entities.segment import Segment, SegmentRead
from app.domain.entities.segment_features import SegmentFeatures, SegmentFeaturesRead
from app.domain.services import segmentation_service
from app.api.routers._shared import security

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
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Segmente une activite specifique."""
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
        count = segmentation_service.segment_activity(session, activity)
        return {"activity_id": str(activity_id), "segments_created": count}
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
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session),
):
    """Retourne les segments d'une activite avec leurs features."""
    user_id = get_current_user_id(token.credentials)

    # Verifier que l'activite appartient a l'utilisateur
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

    segments = session.exec(
        select(Segment)
        .where(Segment.activity_id == activity_id)
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
        "activity_id": str(activity_id),
        "segment_count": len(result),
        "segments": result,
    }
