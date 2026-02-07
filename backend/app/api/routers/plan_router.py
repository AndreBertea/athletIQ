"""
Routes des plans d'entrainement : CRUD, import CSV, Google Calendar.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Form, File, UploadFile
from sqlmodel import Session
from typing import List, Optional
from uuid import UUID
from datetime import date

from app.core.database import get_session
from app.auth.jwt import get_current_user_id
from app.domain.entities import WorkoutPlanRead, WorkoutPlanCreate, WorkoutPlanUpdate
from app.domain.services.workout_plan_service import workout_plan_service
from app.domain.services.csv_import_service import csv_import_service
from app.api.routers._shared import security, extract_token_from_credentials

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/workout-plans", response_model=WorkoutPlanRead)
async def create_workout_plan(
    plan_data: WorkoutPlanCreate,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Cree un nouveau plan d'entrainement"""
    user_id = get_current_user_id(token.credentials)
    return workout_plan_service.create(session, user_id, plan_data)


@router.get("/workout-plans", response_model=List[WorkoutPlanRead])
async def get_workout_plans(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    workout_type: Optional[str] = None,
    is_completed: Optional[bool] = None
):
    """Recupere les plans d'entrainement de l'utilisateur"""
    user_id = get_current_user_id(token.credentials)
    return workout_plan_service.list_plans(
        session, user_id, start_date, end_date, workout_type, is_completed
    )


@router.get("/workout-plans/{plan_id}", response_model=WorkoutPlanRead)
async def get_workout_plan(
    plan_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Recupere un plan d'entrainement specifique"""
    user_id = get_current_user_id(token.credentials)
    try:
        return workout_plan_service.get(session, user_id, plan_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found")


@router.patch("/workout-plans/{plan_id}", response_model=WorkoutPlanRead)
async def update_workout_plan(
    plan_id: UUID,
    plan_updates: WorkoutPlanUpdate,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Met a jour un plan d'entrainement"""
    user_id = get_current_user_id(token.credentials)
    try:
        return workout_plan_service.update(session, user_id, plan_id, plan_updates)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found")


@router.delete("/workout-plans/{plan_id}")
async def delete_workout_plan(
    plan_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime un plan d'entrainement"""
    user_id = get_current_user_id(token.credentials)
    try:
        return workout_plan_service.delete(session, user_id, plan_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workout plan not found")


# ============ IMPORT CSV ============

@router.post("/workout-plans/import-csv")
async def import_workout_plans_csv(
    file: UploadFile = File(...),
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Importe des plans d'entrainement depuis un fichier CSV"""
    user_id = get_current_user_id(token.credentials)
    try:
        content = await file.read()
        return csv_import_service.import_from_upload(session, content, file.filename, UUID(user_id))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import: {str(e)}"
        )


# ============ GOOGLE CALENDAR ============

@router.get("/google-calendar/calendars")
async def get_google_calendars(
    session: Session = Depends(get_session),
    token_credentials: str = Depends(security)
):
    """Recupere les calendriers Google de l'utilisateur"""
    try:
        token = extract_token_from_credentials(token_credentials)
        user_id = get_current_user_id(token)
        return workout_plan_service.get_google_calendars(session, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la recuperation des calendriers: {str(e)}"
        )


@router.post("/google-calendar/export")
async def export_workout_plans_to_google(
    calendar_id: str = Form("primary"),
    session: Session = Depends(get_session),
    token_credentials: str = Depends(security)
):
    """Exporte les plans d'entrainement vers Google Calendar"""
    try:
        token = extract_token_from_credentials(token_credentials)
        user_id = get_current_user_id(token)
        return workout_plan_service.export_plans_to_google(session, user_id, calendar_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'export: {str(e)}"
        )


@router.post("/google-calendar/import")
async def import_google_calendar_as_workout_plans(
    calendar_id: str = Form("primary"),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    token_credentials: str = Depends(security)
):
    """Importe les evenements Google Calendar comme plans d'entrainement"""
    try:
        token = extract_token_from_credentials(token_credentials)
        user_id = get_current_user_id(token)
        return workout_plan_service.import_plans_from_google(
            session, user_id, calendar_id, start_date, end_date
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import: {str(e)}"
        )
