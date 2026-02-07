"""
Service de gestion des donnees : RGPD (suppression/export).
"""
import logging
from uuid import UUID
from datetime import datetime

from sqlmodel import Session, select

from app.domain.entities import User, StravaAuth, Activity, WorkoutPlan

logger = logging.getLogger(__name__)


class DataManagementService:

    # ---- RGPD ----

    def delete_strava_data(self, session: Session, user_id: str) -> dict:
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        if strava_auth:
            session.delete(strava_auth)

        strava_activities = session.exec(
            select(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.strava_id.is_not(None),
            )
        ).all()

        activities_count = len(strava_activities)
        for activity in strava_activities:
            session.delete(activity)

        session.commit()

        return {
            "message": "Donnees Strava supprimees avec succes",
            "deleted_activities": activities_count,
            "strava_auth_deleted": bool(strava_auth),
        }

    def delete_all_user_data(self, session: Session, user_id: str) -> dict:
        activities = session.exec(
            select(Activity).where(Activity.user_id == UUID(user_id))
        ).all()
        activities_count = len(activities)

        plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()
        plans_count = len(plans)

        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()

        for activity in activities:
            session.delete(activity)
        for plan in plans:
            session.delete(plan)
        if strava_auth:
            session.delete(strava_auth)

        session.commit()

        return {
            "message": "Toutes les donnees utilisateur supprimees avec succes",
            "deleted_activities": activities_count,
            "deleted_workout_plans": plans_count,
            "strava_auth_deleted": bool(strava_auth),
        }

    def delete_account(self, session: Session, user_id: str) -> dict:
        user = session.get(User, UUID(user_id))
        if not user:
            raise ValueError("Utilisateur non trouve")

        result = self.delete_all_user_data(session, user_id)

        # Re-fetch user since session may have been flushed
        user = session.get(User, UUID(user_id))
        if user:
            session.delete(user)
            session.commit()

        result["message"] = "Compte et toutes les donnees supprimes avec succes"
        result["account_deleted"] = True
        return result

    def export_user_data(self, session: Session, user_id: str) -> dict:
        user = session.get(User, UUID(user_id))
        if not user:
            raise ValueError("Utilisateur non trouve")

        activities = session.exec(
            select(Activity).where(Activity.user_id == UUID(user_id))
        ).all()

        workout_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()

        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()

        return {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at.isoformat(),
                "is_active": user.is_active,
            },
            "activities": [
                {
                    "id": str(activity.id),
                    "name": activity.name,
                    "activity_type": activity.activity_type,
                    "start_date": activity.start_date.isoformat(),
                    "distance": activity.distance,
                    "moving_time": activity.moving_time,
                    "elapsed_time": activity.elapsed_time,
                    "total_elevation_gain": activity.total_elevation_gain,
                    "average_speed": activity.average_speed,
                    "max_speed": activity.max_speed,
                    "average_heartrate": activity.average_heartrate,
                    "max_heartrate": activity.max_heartrate,
                    "average_cadence": activity.average_cadence,
                    "description": activity.description,
                    "strava_id": activity.strava_id,
                    "location_city": activity.location_city,
                    "location_country": activity.location_country,
                    "created_at": activity.created_at.isoformat(),
                }
                for activity in activities
            ],
            "workout_plans": [
                {
                    "id": str(plan.id),
                    "name": plan.name,
                    "workout_type": plan.workout_type,
                    "planned_date": plan.planned_date.isoformat(),
                    "planned_distance": plan.planned_distance,
                    "planned_duration": plan.planned_duration,
                    "planned_pace": plan.planned_pace,
                    "planned_elevation_gain": plan.planned_elevation_gain,
                    "intensity_zone": plan.intensity_zone,
                    "description": plan.description,
                    "coach_notes": plan.coach_notes,
                    "is_completed": plan.is_completed,
                    "completion_percentage": plan.completion_percentage,
                    "created_at": plan.created_at.isoformat(),
                }
                for plan in workout_plans
            ],
            "strava_connection": {
                "connected": bool(strava_auth),
                "athlete_id": strava_auth.strava_athlete_id if strava_auth else None,
                "scope": strava_auth.scope if strava_auth else None,
                "connected_at": strava_auth.created_at.isoformat() if strava_auth else None,
            }
            if strava_auth
            else None,
            "export_date": datetime.utcnow().isoformat(),
            "export_type": "complete_user_data",
        }



data_management_service = DataManagementService()
