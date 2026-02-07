"""
Service des plans d'entrainement : CRUD, synchronisation Google Calendar.
"""
import json
import logging
import os
from sqlmodel import Session, select
from uuid import UUID
from datetime import date, datetime
from typing import Optional, List

from app.domain.entities import User, WorkoutPlan, WorkoutPlanCreate, WorkoutPlanUpdate
from app.domain.entities.workout_plan import WorkoutType

logger = logging.getLogger(__name__)


class WorkoutPlanService:

    def create(self, session: Session, user_id: str, plan_data: WorkoutPlanCreate) -> WorkoutPlan:
        workout_plan = WorkoutPlan(user_id=UUID(user_id), **plan_data.dict())
        session.add(workout_plan)
        session.commit()
        session.refresh(workout_plan)
        return workout_plan

    def list_plans(
        self,
        session: Session,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        workout_type: Optional[str] = None,
        is_completed: Optional[bool] = None,
    ) -> List[WorkoutPlan]:
        query = select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))

        if start_date:
            query = query.where(WorkoutPlan.planned_date >= start_date)
        if end_date:
            query = query.where(WorkoutPlan.planned_date <= end_date)
        if workout_type:
            query = query.where(WorkoutPlan.workout_type == workout_type)
        if is_completed is not None:
            query = query.where(WorkoutPlan.is_completed == is_completed)

        query = query.order_by(WorkoutPlan.planned_date.desc())
        return session.exec(query).all()

    def get(self, session: Session, user_id: str, plan_id: UUID) -> WorkoutPlan:
        plan = session.exec(
            select(WorkoutPlan).where(
                WorkoutPlan.id == plan_id,
                WorkoutPlan.user_id == UUID(user_id),
            )
        ).first()
        if not plan:
            raise ValueError("Workout plan not found")
        return plan

    def update(
        self, session: Session, user_id: str, plan_id: UUID, plan_updates: WorkoutPlanUpdate
    ) -> WorkoutPlan:
        plan = self.get(session, user_id, plan_id)

        for field, value in plan_updates.dict(exclude_unset=True).items():
            setattr(plan, field, value)

        plan.updated_at = datetime.utcnow()
        session.add(plan)
        session.commit()
        session.refresh(plan)
        return plan

    def delete(self, session: Session, user_id: str, plan_id: UUID) -> dict:
        plan = self.get(session, user_id, plan_id)
        session.delete(plan)
        session.commit()
        return {"message": "Workout plan deleted successfully"}

    def export_to_google(self, session: Session, user_id: str) -> list:
        """Retourne les plans au format attendu par google_calendar_service."""
        workout_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()

        return [
            {
                "workout_type": plan.workout_type,
                "description": plan.description or "",
                "planned_date": plan.planned_date.isoformat(),
                "duration_minutes": plan.planned_duration // 60 if plan.planned_duration else 60,
            }
            for plan in workout_plans
        ]

    def sync_from_google(
        self, session: Session, user_id: str, imported_plans: list
    ) -> dict:
        """Synchronise les plans importes de Google Calendar avec la DB."""
        saved_count = 0
        updated_count = 0
        deleted_count = 0

        existing_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()

        existing_plans_dict = {}
        for plan in existing_plans:
            key = (plan.planned_date, plan.name)
            existing_plans_dict[key] = plan

        for plan_data in imported_plans:
            try:
                event_name = plan_data.get("summary", "Sans titre")
                event_date = datetime.fromisoformat(plan_data["planned_date"]).date()
                key = (event_date, event_name)

                existing_plan = existing_plans_dict.get(key)

                if not existing_plan:
                    workout_plan = WorkoutPlan(
                        user_id=UUID(user_id),
                        name=plan_data.get(
                            "summary",
                            f"Entrainement - {datetime.fromisoformat(plan_data['planned_date']).strftime('%d/%m/%Y')}",
                        ),
                        workout_type=WorkoutType.EASY_RUN,
                        planned_date=event_date,
                        planned_distance=0.0,
                        planned_duration=plan_data.get("duration_minutes", 60) * 60,
                        planned_pace=0.0,
                        planned_elevation_gain=0.0,
                        description=plan_data.get("description", ""),
                        coach_notes=plan_data.get("description", ""),
                        is_completed=False,
                    )
                    session.add(workout_plan)
                    saved_count += 1
                    logger.info(f"Plan cree: {workout_plan.name}")
                else:
                    existing_plan.description = plan_data.get("description", "")
                    existing_plan.coach_notes = plan_data.get("description", "")
                    existing_plan.planned_duration = plan_data.get("duration_minutes", 60) * 60
                    updated_count += 1
                    logger.info(f"Plan mis a jour: {existing_plan.name}")

                existing_plans_dict.pop(key, None)

            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde du plan: {e}")
                continue

        for key, plan in existing_plans_dict.items():
            try:
                logger.info(f"Suppression du plan: {plan.name} (plus dans Google Calendar)")
                session.delete(plan)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du plan: {e}")
                continue

        session.commit()

        return {
            "imported_count": saved_count,
            "updated_count": updated_count,
            "deleted_count": deleted_count,
            "total_found": len(imported_plans),
        }


    def import_from_google(
        self,
        session: Session,
        user_id: str,
        imported_plans: list,
        calendar_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Synchronise les plans depuis Google Calendar et cree un fichier JSON de log."""
        sync_result = self.sync_from_google(session, user_id, imported_plans)

        # Ecriture du fichier JSON de log
        user = session.exec(select(User).where(User.id == UUID(user_id))).first()

        data_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(data_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"imported_calendar_{timestamp}.json"
        filepath = os.path.join(data_dir, filename)

        json_data = {
            "import_info": {
                "import_date": datetime.now().isoformat(),
                "calendar_id": calendar_id,
                "time_range": {"start_date": start_date, "end_date": end_date},
                "total_events_imported": len(imported_plans),
            },
            "imported_events": [
                {
                    "summary": plan_data.get("summary", "Sans titre"),
                    "description": plan_data.get("description", ""),
                    "planned_date": plan_data.get("planned_date"),
                    "duration_minutes": plan_data.get("duration_minutes", 60),
                    "is_completed": False,
                    "source": "google_calendar",
                }
                for plan_data in imported_plans
            ],
            "user_info": {
                "user_id": str(user_id),
                "email": user.email if user else "unknown",
                "full_name": user.full_name if user else "unknown",
            },
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Fichier JSON cree: {filepath}")

        return {
            "success": True,
            "imported_count": sync_result["imported_count"],
            "updated_count": sync_result["updated_count"],
            "deleted_count": sync_result["deleted_count"],
            "total_found": sync_result["total_found"],
            "json_file_created": filename,
            "message": (
                f"Synchronisation terminee: {sync_result['imported_count']} crees, "
                f"{sync_result['updated_count']} mis a jour, "
                f"{sync_result['deleted_count']} supprimes. Fichier JSON cree: {filename}"
            ),
        }


    # ---- Orchestration Google Calendar ----

    def get_google_calendars(self, session: Session, user_id: str) -> dict:
        """Recupere les calendriers Google de l'utilisateur."""
        from app.domain.services.google_calendar_service import google_calendar_service
        decrypted_token = auth_service.get_valid_google_token(session, user_id)
        calendars = google_calendar_service.get_user_calendars(decrypted_token)
        return {"calendars": calendars}

    def export_plans_to_google(self, session: Session, user_id: str, calendar_id: str) -> dict:
        """Exporte les plans d'entrainement vers Google Calendar."""
        from app.domain.services.google_calendar_service import google_calendar_service
        decrypted_token = auth_service.get_valid_google_token(session, user_id)
        plans_data = self.export_to_google(session, user_id)

        if not plans_data:
            return {
                "success": True,
                "message": "Aucun plan d'entrainement a exporter",
                "exported_count": 0,
                "total_count": 0,
            }

        return google_calendar_service.export_workout_plans_to_google(
            plans_data, calendar_id, decrypted_token
        )

    def import_plans_from_google(
        self,
        session: Session,
        user_id: str,
        calendar_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Importe les evenements Google Calendar comme plans d'entrainement."""
        from app.domain.services.google_calendar_service import google_calendar_service
        decrypted_token = auth_service.get_valid_google_token(session, user_id)
        imported_plans = google_calendar_service.import_google_calendar_as_workout_plans(
            calendar_id, start_date, end_date, decrypted_token
        )
        return self.import_from_google(session, user_id, imported_plans, calendar_id, start_date, end_date)


workout_plan_service = WorkoutPlanService()
