"""
Routes check-in readiness : POST today, GET today, GET history, GET score.
"""
from __future__ import annotations

import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.routers._shared import security
from app.auth.jwt import get_current_user_id
from app.core.database import get_session
from app.domain.entities.daily_checkin import (
    DailyCheckinCreate,
    DailyCheckinRead,
    ReadinessScore,
)
from app.domain.services import checkin_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/checkin", tags=["checkin"])


@router.post("", response_model=DailyCheckinRead, status_code=status.HTTP_201_CREATED)
def post_today(
    payload: DailyCheckinCreate,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Cree ou met a jour la saisie du jour (upsert)."""
    user_id = UUID(get_current_user_id(token.credentials))
    entry = checkin_service.upsert_today(db, user_id, payload)
    return DailyCheckinRead.model_validate(entry, from_attributes=True)


@router.get("/today", response_model=DailyCheckinRead | None)
def get_today(
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Retourne la saisie du jour si elle existe (sinon null)."""
    user_id = UUID(get_current_user_id(token.credentials))
    entry = checkin_service.get_today(db, user_id)
    if entry is None:
        return None
    return DailyCheckinRead.model_validate(entry, from_attributes=True)


@router.get("/history", response_model=List[DailyCheckinRead])
def get_history(
    days: int = Query(default=30, ge=1, le=365),
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Historique des N derniers jours (max 365)."""
    user_id = UUID(get_current_user_id(token.credentials))
    entries = checkin_service.get_history(db, user_id, days=days)
    return [DailyCheckinRead.model_validate(e, from_attributes=True) for e in entries]


@router.get("/score", response_model=ReadinessScore)
def get_score(
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Score readiness consolide (calibration ou stable selon nb de jours)."""
    user_id = UUID(get_current_user_id(token.credentials))
    return checkin_service.compute_score(db, user_id)
