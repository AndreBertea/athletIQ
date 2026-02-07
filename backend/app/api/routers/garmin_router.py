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
from app.domain.services.garmin_sync_service import sync_daily_data
from app.api.routers._shared import security, limiter

logger = logging.getLogger(__name__)

router = APIRouter()


class GarminLoginRequest(BaseModel):
    email: EmailStr
    password: str


# ============ AUTH GARMIN ============

@router.post("/auth/garmin/login")
@limiter.limit("3/hour")
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
    days_back: int = Query(default=30, ge=1, le=365),
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
