"""
Service d'activites : filtrage, pagination, statistiques, transformation, mise a jour de type.
"""
import logging
from sqlmodel import Session, select, func
from uuid import UUID
from datetime import datetime, timedelta
from typing import Optional

from app.domain.entities import Activity, ActivityStats, StravaAuth
from app.domain.entities.activity import ActivityType
from app.domain.services.detailed_strava_service import detailed_strava_service
from app.domain.services.auto_enrichment_service import auto_enrichment_service
from app.domain.services.strava_sync_service import strava_sync_service

logger = logging.getLogger(__name__)

VALID_ACTIVITY_TYPES = [
    'Run', 'TrailRun', 'Ride', 'Swim', 'Walk', 'RacketSport', 'Tennis',
    'Badminton', 'Squash', 'Padel', 'WeightTraining', 'RockClimbing',
    'Hiking', 'Yoga', 'Pilates', 'Crossfit', 'Gym', 'VirtualRun',
    'VirtualRide', 'Other'
]


def _activity_to_enriched_dict(a: Activity) -> dict:
    return {
        "activity_id": a.strava_id,
        "name": a.name,
        "sport_type": a.activity_type.value if a.activity_type else None,
        "distance_m": a.distance,
        "moving_time_s": a.moving_time,
        "elapsed_time_s": a.elapsed_time,
        "elev_gain_m": a.total_elevation_gain,
        "start_date_utc": a.start_date.isoformat() if a.start_date else None,
        "avg_speed_m_s": a.average_speed,
        "max_speed_m_s": a.max_speed,
        "avg_heartrate_bpm": a.average_heartrate,
        "max_heartrate_bpm": a.max_heartrate,
        "avg_cadence": a.average_cadence,
        "description": a.description,
        "location_city": a.location_city,
        "location_country": a.location_country,
    }


class ActivityService:

    def get_activities_paginated(
        self,
        session: Session,
        user_id: str,
        page: int,
        per_page: int,
        activity_type: Optional[str] = None,
        date_from: Optional[str] = None,
    ) -> dict:
        base_query = select(Activity).where(Activity.user_id == UUID(user_id))

        if date_from:
            try:
                cutoff = datetime.fromisoformat(date_from)
                base_query = base_query.where(Activity.start_date >= cutoff)
            except ValueError:
                pass

        if activity_type:
            if activity_type == "running_activities":
                base_query = base_query.where(
                    Activity.activity_type.in_([ActivityType.RUN, ActivityType.TRAIL_RUN])
                )
            else:
                base_query = base_query.where(Activity.activity_type == activity_type)

        total = session.exec(select(func.count()).select_from(base_query.subquery())).one()
        offset = (page - 1) * per_page
        query = base_query.order_by(Activity.start_date.desc()).offset(offset).limit(per_page)
        activities = session.exec(query).all()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        return {
            "items": activities,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": total_pages,
        }

    def get_activity_stats(
        self, session: Session, user_id: str, period_days: int
    ) -> ActivityStats:
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)
        activities = session.exec(
            select(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.start_date >= cutoff_date,
            )
        ).all()

        if not activities:
            return ActivityStats(
                total_activities=0,
                total_distance=0,
                total_time=0,
                average_pace=0,
                activities_by_type={},
                distance_by_month={},
            )

        total_distance = sum(act.distance for act in activities) / 1000
        total_time = sum(act.moving_time for act in activities)

        total_weighted_pace = 0
        total_distance_with_pace = 0
        for activity in activities:
            if activity.average_pace and activity.distance > 0:
                distance_km = activity.distance / 1000
                total_weighted_pace += activity.average_pace * distance_km
                total_distance_with_pace += distance_km

        avg_pace = total_weighted_pace / total_distance_with_pace if total_distance_with_pace > 0 else 0

        activities_by_type = {}
        for activity in activities:
            act_type = activity.activity_type.value
            activities_by_type[act_type] = activities_by_type.get(act_type, 0) + 1

        distance_by_month = {}
        for activity in activities:
            month_key = activity.start_date.strftime("%Y-%m")
            distance_by_month[month_key] = distance_by_month.get(month_key, 0) + (activity.distance / 1000)

        return ActivityStats(
            total_activities=len(activities),
            total_distance=round(total_distance, 1),
            total_time=total_time,
            average_pace=round(avg_pace, 2),
            activities_by_type=activities_by_type,
            distance_by_month=distance_by_month,
        )

    def get_enrichment_status(self, session: Session, user_id: str) -> dict:
        total = session.exec(
            select(func.count()).select_from(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.strava_id.is_not(None),
            )
        ).one()

        enriched = session.exec(
            select(func.count()).select_from(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.strava_id.is_not(None),
                Activity.streams_data.is_not(None),
            )
        ).one()

        pending = max(0, total - enriched)
        percentage = round((enriched / total) * 100) if total > 0 else 0

        quota_status = detailed_strava_service.quota_manager.get_status()
        safe_quota = {
            "daily_used": quota_status["daily_used"],
            "daily_limit": quota_status["daily_limit"],
            "per_15min_used": quota_status["per_15min_used"],
            "per_15min_limit": quota_status["per_15min_limit"],
        }
        can_enrich = pending > 0 and safe_quota["daily_used"] < safe_quota["daily_limit"]

        return {
            "total_activities": total,
            "strava_activities": total,
            "enriched_activities": enriched,
            "pending_activities": pending,
            "enrichment_percentage": percentage,
            "quota_status": safe_quota,
            "can_enrich_more": can_enrich,
            "auto_enrichment_running": auto_enrichment_service.is_running,
        }

    def get_enriched_activities_paginated(
        self,
        session: Session,
        user_id: str,
        page: int,
        per_page: int,
        sport_type: Optional[str] = None,
        date_from: Optional[str] = None,
    ) -> dict:
        base_query = select(Activity).where(
            Activity.user_id == UUID(user_id),
            Activity.strava_id.is_not(None),
            Activity.streams_data.is_not(None),
        )

        if date_from:
            try:
                cutoff = datetime.fromisoformat(date_from)
                base_query = base_query.where(Activity.start_date >= cutoff)
            except ValueError:
                pass

        if sport_type:
            base_query = base_query.where(Activity.activity_type == sport_type)

        total = session.exec(select(func.count()).select_from(base_query.subquery())).one()
        offset = (page - 1) * per_page
        query = base_query.order_by(Activity.start_date.desc()).offset(offset).limit(per_page)
        activities = session.exec(query).all()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        items = [_activity_to_enriched_dict(a) for a in activities]

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": total_pages,
        }

    def get_enriched_activity_stats(
        self,
        session: Session,
        user_id: str,
        period_days: int,
        sport_type: Optional[str] = None,
    ) -> dict:
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)

        query = select(Activity).where(
            Activity.user_id == UUID(user_id),
            Activity.start_date >= cutoff_date,
        )
        if sport_type:
            query = query.where(Activity.activity_type == sport_type)

        query = query.order_by(Activity.start_date.desc())
        activities = session.exec(query).all()

        total_distance_km = sum(a.distance or 0 for a in activities) / 1000
        total_time_hours = sum(a.moving_time or 0 for a in activities) / 3600

        activities_by_sport_type = {}
        distance_by_sport_type = {}
        time_by_sport_type = {}

        activity_list = []
        for a in activities:
            st = a.activity_type.value if a.activity_type else "Unknown"
            activities_by_sport_type[st] = activities_by_sport_type.get(st, 0) + 1
            distance_by_sport_type[st] = distance_by_sport_type.get(st, 0) + (a.distance or 0) / 1000
            time_by_sport_type[st] = time_by_sport_type.get(st, 0) + (a.moving_time or 0) / 3600

            activity_list.append({
                "activity_id": a.strava_id,
                "name": a.name,
                "sport_type": st,
                "distance_m": a.distance,
                "moving_time_s": a.moving_time,
                "start_date_utc": a.start_date.isoformat() if a.start_date else None,
                "elev_gain_m": a.total_elevation_gain,
                "avg_speed_m_s": a.average_speed,
                "avg_heartrate_bpm": a.average_heartrate,
            })

        return {
            "total_activities": len(activities),
            "total_distance_km": total_distance_km,
            "total_time_hours": total_time_hours,
            "activities_by_sport_type": activities_by_sport_type,
            "distance_by_sport_type": distance_by_sport_type,
            "time_by_sport_type": time_by_sport_type,
            "activities": activity_list,
        }

    def get_enriched_activity(self, session: Session, user_id: str, activity_id: int) -> dict:
        activity = session.exec(
            select(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.strava_id == activity_id,
            )
        ).first()

        if not activity:
            raise ValueError("Activite enrichie non trouvee")

        return _activity_to_enriched_dict(activity)

    def get_enriched_activity_streams(self, session: Session, user_id: str, activity_id: int) -> dict:
        activity = session.exec(
            select(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.strava_id == activity_id,
            )
        ).first()

        if not activity:
            raise ValueError("Activite non trouvee")

        if not activity.streams_data:
            return {"activity_id": activity_id, "streams": {}, "message": "Aucun stream disponible pour cette activite"}

        streams_clean = {k: v for k, v in activity.streams_data.items() if k != "segment_efforts"}
        return {"activity_id": activity_id, "streams": streams_clean}

    def check_strava_connected(self, session: Session, user_id: str) -> None:
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        if not strava_auth:
            raise ValueError("Strava not connected")

    def enrich_batch(self, session: Session, user_id: str, max_activities: int) -> dict:
        self.check_strava_connected(session, user_id)

        result = detailed_strava_service.batch_enrich_activities(session, user_id, max_activities)

        quota = result.get("quota_status", {})
        if quota.get("daily_used", 0) >= quota.get("daily_limit", 1000):
            result["message"] = "Quota API Strava journalier atteint. Reessayez demain."
            result["rate_limited"] = True
        else:
            result["rate_limited"] = False

        return result

    def get_activity_by_id(self, session: Session, user_id: str, activity_id: UUID) -> Activity:
        activity = session.exec(
            select(Activity).where(
                Activity.id == activity_id,
                Activity.user_id == UUID(user_id),
            )
        ).first()
        if not activity:
            raise ValueError("Activite non trouvee")
        return activity

    def get_activity_streams(self, session: Session, user_id: str, activity_id: UUID) -> dict:
        activity = self.get_activity_by_id(session, user_id, activity_id)
        if not activity.streams_data:
            raise ValueError("Donnees detaillees non disponibles pour cette activite")
        return {
            "activity_id": str(activity_id),
            "streams_data": activity.streams_data,
            "laps_data": activity.laps_data,
        }

    def enrich_single(self, session: Session, user_id: str, activity_id: UUID) -> dict:
        activity = self.get_activity_by_id(session, user_id, activity_id)

        if not activity.strava_id:
            raise ValueError("Cette activite n'est pas liee a Strava")

        success = detailed_strava_service.enrich_activity_with_details(session, user_id, activity)

        if not success:
            raise RuntimeError("Echec de l'enrichissement de l'activite")

        return {
            "message": "Activite enrichie avec succes",
            "activity_id": str(activity_id),
            "has_streams": bool(activity.streams_data),
            "has_laps": bool(activity.laps_data),
            "quota_status": detailed_strava_service.quota_manager.get_status(),
        }

    def prioritize_activity(self, session: Session, user_id: str, activity_id: UUID) -> dict:
        activity = self.get_activity_by_id(session, user_id, activity_id)

        if not activity.strava_id:
            raise ValueError("Cette activite n'est pas liee a Strava")

        if activity.streams_data:
            return {
                "message": "Cette activite est deja enrichie",
                "activity_id": str(activity_id),
            }

        success = auto_enrichment_service.prioritize_activity(str(activity_id), user_id)

        return {
            "message": "Activite ajoutee en priorite haute" if success else "Activite deja en queue",
            "activity_id": str(activity_id),
            "queue_status": auto_enrichment_service.get_queue_status(),
        }

    def update_activity_type(
        self, session: Session, user_id: str, activity_id_str: str, activity_type: str
    ) -> dict:
        # Resolve activity by UUID or strava_id
        activity = None
        try:
            activity_uuid = UUID(activity_id_str)
            activity = session.exec(
                select(Activity).where(
                    Activity.id == activity_uuid,
                    Activity.user_id == UUID(user_id),
                )
            ).first()
        except ValueError:
            try:
                strava_id = int(activity_id_str)
                activity = session.exec(
                    select(Activity).where(
                        Activity.strava_id == strava_id,
                        Activity.user_id == UUID(user_id),
                    )
                ).first()
            except ValueError:
                raise ValueError("L'ID de l'activite doit etre un UUID valide ou un ID numerique Strava")

        if not activity:
            raise ValueError("Activite non trouvee")

        if activity_type not in VALID_ACTIVITY_TYPES:
            raise ValueError(f"Type d'activite invalide. Types valides: {', '.join(VALID_ACTIVITY_TYPES)}")

        old_type = activity.activity_type

        activity.activity_type = activity_type
        activity.updated_at = datetime.utcnow()

        session.add(activity)
        session.commit()
        session.refresh(activity)

        logger.info(f"Type d'activite {activity.id} modifie: {old_type} -> {activity_type} (utilisateur: {user_id})")

        return {
            "message": "Type d'activite mis a jour avec succes",
            "activity_id": str(activity.id),
            "old_type": old_type,
            "new_type": activity_type,
            "activity": {
                "id": str(activity.id),
                "name": activity.name,
                "activity_type": activity.activity_type,
                "start_date": activity.start_date.isoformat(),
                "distance": activity.distance,
                "moving_time": activity.moving_time,
            },
        }


    def sync_and_enrich(self, session: Session, user_id: str, days_back: int) -> dict:
        """Synchronise les activites Strava puis lance l'enrichissement automatique."""
        result = strava_sync_service.sync_activities(session, user_id, days_back)

        try:
            enrich_result = detailed_strava_service.batch_enrich_activities(
                session, user_id, max_activities=50
            )
            quota = enrich_result.get("quota_status", {})

            result["enrichment"] = {
                "enriched_count": enrich_result.get("enriched_count", 0),
                "failed_count": enrich_result.get("failed_count", 0),
                "rate_limited": quota.get("daily_used", 0) >= quota.get("daily_limit", 1000),
            }

            if result["enrichment"]["rate_limited"]:
                result["enrichment"]["message"] = "Quota API Strava journalier atteint. Reessayez demain."
            else:
                result["enrichment"]["message"] = f"{enrich_result.get('enriched_count', 0)} activites enrichies automatiquement"

            logger.info(f"Auto-enrichissement: {enrich_result.get('enriched_count', 0)} activites enrichies")
        except Exception as enrich_error:
            logger.warning(f"Auto-enrichissement echoue (non bloquant): {enrich_error}")
            result["enrichment"] = {"message": "Enrichissement automatique differe", "enriched_count": 0}

        return result


activity_service = ActivityService()
