"""
Routes donnees : RGPD (suppression/export), analyse, prediction GPX.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlmodel import Session
from datetime import datetime

from app.core.database import get_session
from app.auth.jwt import get_current_user_id
from app.domain.services.data_management_service import data_management_service
from app.api.routers._shared import security

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ RGPD - SUPPRESSION DES DONNEES ============

@router.delete("/data/strava")
async def delete_strava_data(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime toutes les donnees Strava de l'utilisateur (conformite RGPD)"""
    user_id = get_current_user_id(token.credentials)
    try:
        return data_management_service.delete_strava_data(session, user_id)
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression des donnees Strava: {str(e)}"
        )


@router.delete("/data/all")
async def delete_all_user_data(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime toutes les donnees de l'utilisateur SAUF le compte (conformite RGPD)"""
    user_id = get_current_user_id(token.credentials)
    try:
        return data_management_service.delete_all_user_data(session, user_id)
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression des donnees: {str(e)}"
        )


@router.delete("/account")
async def delete_account(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime completement le compte utilisateur et toutes ses donnees (conformite RGPD)"""
    user_id = get_current_user_id(token.credentials)
    try:
        return data_management_service.delete_account(session, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression du compte: {str(e)}"
        )


@router.get("/data/export")
async def export_user_data(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Exporte toutes les donnees de l'utilisateur au format JSON (conformite RGPD)"""
    user_id = get_current_user_id(token.credentials)
    try:
        export_data = data_management_service.export_user_data(session, user_id)
        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename=athletiq_data_export_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'export des donnees: {str(e)}"
        )

