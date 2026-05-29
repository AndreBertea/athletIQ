"""
Service d'activites : filtrage, pagination, statistiques, transformation, mise a jour de type.
"""
import logging
import json
from sqlmodel import Session, select, func
from sqlalchemy import String, cast, or_
from sqlalchemy.orm import defer
from uuid import UUID
from datetime import datetime, timedelta
from typing import Any, Optional

from app.domain.entities import Activity, ActivityStats, StravaAuth
from app.domain.entities.activity import ActivitySource, ActivityType
from app.domain.entities.activity_weather import ActivityWeather
from app.domain.entities.fit_metrics import FitMetrics
from app.domain.services.detailed_strava_service import detailed_strava_service
from app.domain.services.auto_enrichment_service import auto_enrichment_service
from app.domain.services.strava_sync_service import strava_sync_service

logger = logging.getLogger(__name__)

VALID_ACTIVITY_TYPES = [activity_type.value for activity_type in ActivityType]


def streams_data_usable_clause():
    """SQL clause for activities with actual stream payloads, not JSON null."""
    return (
        Activity.streams_data.is_not(None),
        cast(Activity.streams_data, String) != "null",
    )


def streams_data_missing_clause():
    """SQL clause for activities that need stream enrichment."""
    return or_(
        Activity.streams_data.is_(None),
        cast(Activity.streams_data, String) == "null",
    )


def normalize_streams_data(raw: Any) -> Optional[dict]:
    """Return stream dict or None, handling SQLite JSON null stored as text."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if raw.strip().lower() == "null":
            return None
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(raw, dict) or not raw:
        return None
    return raw


def _activity_to_enriched_dict(a: Activity) -> dict:
    """Serialize the activity summary independently from provider-specific data."""
    activity_type = a.activity_type_override if a.activity_type_override else a.activity_type
    sport_type = activity_type.value if activity_type else None

    return {
        "id": str(a.id),
        # Stable application identity. External provider IDs remain separate below.
        "activity_id": str(a.id),
        "source": a.source,
        "strava_id": a.strava_id,
        "garmin_activity_id": a.garmin_activity_id,
        "name": a.name,
        "sport_type": sport_type,
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
        "calories_kcal": a.calories,
        "description": a.description,
        "location_city": a.location_city,
        "location_country": a.location_country,
        "summary_polyline": a.summary_polyline,
        "polyline": a.polyline,
        "start_latlng": a.start_latlng,
        "end_latlng": a.end_latlng,
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
        base_query = select(Activity).where(
            Activity.user_id == UUID(user_id),
            Activity.source == ActivitySource.GARMIN.value,
        )

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

        # Batch-check des sources de données
        activity_uuids = [a.id for a in activities]
        weather_ids: set = set()
        garmin_ids: set = set()
        if activity_uuids:
            weather_ids = set(
                session.exec(
                    select(ActivityWeather.activity_id).where(
                        ActivityWeather.activity_id.in_(activity_uuids)
                    )
                ).all()
            )
            garmin_ids = set(
                session.exec(
                    select(FitMetrics.activity_id).where(
                        FitMetrics.activity_id.in_(activity_uuids)
                    )
                ).all()
            )

        items = []
        for a in activities:
            d = a.model_dump() if hasattr(a, 'model_dump') else a.dict()
            d["has_strava"] = a.strava_id is not None
            d["has_weather"] = a.id in weather_ids
            d["has_garmin"] = a.garmin_activity_id is not None
            d["has_fit_metrics"] = a.id in garmin_ids
            d["has_streams"] = normalize_streams_data(a.streams_data) is not None
            items.append(d)

        return {
            "items": items,
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
                Activity.source == ActivitySource.GARMIN.value,
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
                *streams_data_usable_clause(),
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
        # This is the compact display feed consumed by the activity list and
        # dashboard charts. Activities remain visible before optional streams,
        # FIT metrics or weather enrichment exists.
        base_query = select(Activity).where(
            Activity.user_id == UUID(user_id),
            Activity.source == ActivitySource.GARMIN.value,
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
        query = (
            base_query
            .options(defer(Activity.streams_data), defer(Activity.laps_data))
            .order_by(Activity.start_date.desc())
            .offset(offset)
            .limit(per_page)
        )
        activities = session.exec(query).all()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        # Collecter les UUIDs pour batch-check des sources de données
        activity_uuids = [a.id for a in activities]

        weather_ids: set = set()
        garmin_ids: set = set()
        stream_ids: set = set()
        if activity_uuids:
            weather_ids = set(
                session.exec(
                    select(ActivityWeather.activity_id).where(
                        ActivityWeather.activity_id.in_(activity_uuids)
                    )
                ).all()
            )
            garmin_ids = set(
                session.exec(
                    select(FitMetrics.activity_id).where(
                        FitMetrics.activity_id.in_(activity_uuids)
                    )
                ).all()
            )
            stream_ids = set(
                session.exec(
                    select(Activity.id).where(
                        Activity.id.in_(activity_uuids),
                        *streams_data_usable_clause(),
                    )
                ).all()
            )

        items = []
        for a in activities:
            d = _activity_to_enriched_dict(a)
            d["has_strava"] = a.strava_id is not None
            d["has_weather"] = a.id in weather_ids
            d["has_garmin"] = a.garmin_activity_id is not None
            d["has_fit_metrics"] = a.id in garmin_ids
            d["has_streams"] = a.id in stream_ids
            items.append(d)

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
            Activity.source == ActivitySource.GARMIN.value,
            Activity.start_date >= cutoff_date,
        )
        if sport_type:
            query = query.where(Activity.activity_type == sport_type)

        query = (
            query
            .options(defer(Activity.streams_data), defer(Activity.laps_data))
            .order_by(Activity.start_date.desc())
        )
        activities = session.exec(query).all()

        total_distance_km = sum(a.distance or 0 for a in activities) / 1000
        total_time_hours = sum(a.moving_time or 0 for a in activities) / 3600

        activities_by_sport_type = {}
        distance_by_sport_type = {}
        time_by_sport_type = {}

        activity_list = []
        for a in activities:
            activity_type = a.activity_type_override if a.activity_type_override else a.activity_type
            st = activity_type.value if activity_type else "Unknown"
            activities_by_sport_type[st] = activities_by_sport_type.get(st, 0) + 1
            distance_by_sport_type[st] = distance_by_sport_type.get(st, 0) + (a.distance or 0) / 1000
            time_by_sport_type[st] = time_by_sport_type.get(st, 0) + (a.moving_time or 0) / 3600

            activity_list.append({
                "activity_id": str(a.id),
                "source": a.source,
                "strava_id": a.strava_id,
                "garmin_activity_id": a.garmin_activity_id,
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

    def get_enriched_activity(self, session: Session, user_id: str, activity_id: str) -> dict:
        activity = self._get_summary_activity(session, user_id, activity_id)

        if not activity:
            raise ValueError("Activite non trouvee")

        return _activity_to_enriched_dict(activity)

    def _get_summary_activity(self, session: Session, user_id: str, activity_id: str) -> Optional[Activity]:
        """Resolve an activity by application UUID or either provider ID."""
        user_uuid = UUID(user_id)
        try:
            activity_uuid = UUID(str(activity_id))
            return session.exec(
                select(Activity)
                .options(defer(Activity.streams_data), defer(Activity.laps_data))
                .where(
                    Activity.user_id == user_uuid,
                    Activity.source == ActivitySource.GARMIN.value,
                    Activity.id == activity_uuid,
                )
            ).first()
        except ValueError:
            pass

        try:
            external_id = int(activity_id)
        except (ValueError, TypeError):
            return None

        return session.exec(
            select(Activity)
            .options(defer(Activity.streams_data), defer(Activity.laps_data))
            .where(
                Activity.user_id == user_uuid,
                Activity.source == ActivitySource.GARMIN.value,
                or_(
                    Activity.strava_id == external_id,
                    Activity.garmin_activity_id == external_id,
                ),
            )
        ).first()

    def get_enriched_activity_streams(self, session: Session, user_id: str, activity_id: str) -> dict:
        activity = self._get_summary_activity(session, user_id, activity_id)

        if not activity:
            raise ValueError("Activite non trouvee")

        streams = normalize_streams_data(activity.streams_data)
        if not streams:
            return {"activity_id": activity_id, "streams": {}, "message": "Aucun stream disponible pour cette activite"}

        streams_clean = {}
        for k, v in streams.items():
            if k == "segment_efforts":
                continue
            # Dérouler le format Strava {data: [...], series_type, resolution} en tableau brut
            if isinstance(v, dict) and "data" in v:
                streams_clean[k] = v["data"]
            else:
                streams_clean[k] = v
        return {"activity_id": activity_id, "streams": streams_clean, "laps_data": activity.laps_data}

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
                Activity.source == ActivitySource.GARMIN.value,
            )
        ).first()
        if not activity:
            raise ValueError("Activite non trouvee")
        return activity

    def get_activity_streams(self, session: Session, user_id: str, activity_id: UUID) -> dict:
        activity = self.get_activity_by_id(session, user_id, activity_id)
        streams = normalize_streams_data(activity.streams_data)
        if not streams:
            raise ValueError("Donnees detaillees non disponibles pour cette activite")
        return {
            "activity_id": str(activity_id),
            "streams_data": streams,
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
            "has_streams": bool(normalize_streams_data(activity.streams_data)),
            "has_laps": bool(activity.laps_data),
            "quota_status": detailed_strava_service.quota_manager.get_status(),
        }

    def prioritize_activity(self, session: Session, user_id: str, activity_id: UUID) -> dict:
        activity = self.get_activity_by_id(session, user_id, activity_id)

        if not activity.strava_id:
            raise ValueError("Cette activite n'est pas liee a Strava")

        if normalize_streams_data(activity.streams_data):
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
        # Resolve activity by UUID or Garmin provider id in Garmin-only mode.
        activity = None
        try:
            activity_uuid = UUID(activity_id_str)
            activity = session.exec(
                select(Activity).where(
                    Activity.id == activity_uuid,
                    Activity.user_id == UUID(user_id),
                    Activity.source == ActivitySource.GARMIN.value,
                )
            ).first()
        except ValueError:
            try:
                garmin_activity_id = int(activity_id_str)
                activity = session.exec(
                    select(Activity).where(
                        Activity.garmin_activity_id == garmin_activity_id,
                        Activity.user_id == UUID(user_id),
                        Activity.source == ActivitySource.GARMIN.value,
                    )
                ).first()
            except ValueError:
                raise ValueError("L'ID de l'activite doit etre un UUID valide ou un ID numerique Garmin")

        if not activity:
            raise ValueError("Activite non trouvee")

        if activity_type not in VALID_ACTIVITY_TYPES:
            raise ValueError(f"Type d'activite invalide. Types valides: {', '.join(VALID_ACTIVITY_TYPES)}")

        old_override = activity.activity_type_override
        resolved_activity_type = ActivityType(activity_type)
        activity.activity_type_override = resolved_activity_type
        activity.updated_at = datetime.utcnow()

        session.add(activity)
        session.commit()
        session.refresh(activity)

        logger.info(f"Type override {activity.id} modifie: {old_override} -> {resolved_activity_type} (utilisateur: {user_id})")

        return {
            "message": "Type d'activite mis a jour avec succes",
            "activity_id": str(activity.id),
            "old_type": old_override.value if old_override else None,
            "new_type": resolved_activity_type.value,
            "activity": {
                "id": str(activity.id),
                "name": activity.name,
                "activity_type": activity.activity_type,
                "start_date": activity.start_date.isoformat(),
                "distance": activity.distance,
                "moving_time": activity.moving_time,
            },
        }


    def auto_correct_activity_types(self, session: Session, user_id: str) -> dict:
        """Analyse les noms et descriptions des activités pour proposer des corrections de type."""
        # Dictionnaire des mots-clés → type d'activité
        # Note: Utiliser UNIQUEMENT les types disponibles dans ActivityType enum
        keyword_map = {
            # Trail / Cross
            'trail': ActivityType.TRAIL_RUN,
            'trail run': ActivityType.TRAIL_RUN,
            'trailrun': ActivityType.TRAIL_RUN,
            'sentier': ActivityType.TRAIL_RUN,
            'montagne': ActivityType.TRAIL_RUN,
            'cross': ActivityType.TRAIL_RUN,
            'off-road': ActivityType.TRAIL_RUN,

            # Padel
            'padel': ActivityType.PADEL,
            'pádel': ActivityType.PADEL,

            # Natation
            'swim': ActivityType.SWIM,
            'natation': ActivityType.SWIM,
            'piscine': ActivityType.SWIM,
            'eau': ActivityType.SWIM,

            # Vélo / Ride
            'ride': ActivityType.RIDE,
            'vélo': ActivityType.RIDE,
            'bike': ActivityType.RIDE,
            'cycling': ActivityType.RIDE,

            # Marche / Walk
            'walk': ActivityType.WALK,
            'marche': ActivityType.WALK,
            'rando': ActivityType.WALK,
            'randonnée': ActivityType.WALK,
            'hiking': ActivityType.WALK,
        }

        activities = session.exec(
            select(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.source == ActivitySource.GARMIN.value,
            )
        ).all()

        suggestions = []
        manual_review = []

        standard_time_prefixes = (
            "morning",
            "afternoon",
            "evening",
            "lunch",
            "night",
            "early morning",
        )
        standard_sport_names = (
            "run",
            "ride",
            "walk",
            "swim",
            "trail run",
        )
        standard_french_names = (
            "course à pied le matin",
            "course à pied l'après-midi",
            "course à pied en soirée",
            "course à pied le soir",
            "course à pied à midi",
            "course à pied de nuit",
        )

        def is_standard_strava_name(name: str) -> bool:
            normalized_name = " ".join(name.lower().strip().replace("’", "'").split())
            is_standard_english = any(
                normalized_name == f"{prefix} {sport_name}"
                for prefix in standard_time_prefixes
                for sport_name in standard_sport_names
            )
            return is_standard_english or normalized_name in standard_french_names

        for activity in activities:
            # Analyse du titre et description
            name = activity.name or ""
            description = activity.description or ""
            text_to_analyze = name.lower() + " " + description.lower()

            # Cherche les mots-clés
            suggested_type = None
            matched_keywords = []

            for keyword, activity_type in keyword_map.items():
                if keyword in text_to_analyze:
                    suggested_type = activity_type
                    matched_keywords.append(keyword)
                    break  # Première correspondance (ordre de priorité)

            # Propose une correction seulement si:
            # 1. Un mot-clé a été trouvé
            # 2. Le type détecté est différent du type actuel ET du type override
            current_type = activity.activity_type_override if activity.activity_type_override else activity.activity_type

            if suggested_type and suggested_type != current_type:
                suggestions.append({
                    "activity_id": str(activity.id),
                    "strava_id": activity.strava_id,
                    "name": name,
                    "current_type": current_type.value if current_type else None,
                    "suggested_type": suggested_type.value,
                    "matched_keywords": matched_keywords,
                    "description": description,
                    "start_date": activity.start_date.isoformat() if activity.start_date else None,
                    "distance": activity.distance,
                })
                continue

            if (
                not activity.activity_type_override
                and not suggested_type
                and name
                and not is_standard_strava_name(name)
            ):
                manual_review.append({
                    "activity_id": str(activity.id),
                    "strava_id": activity.strava_id,
                    "name": name,
                    "current_type": current_type.value if current_type else None,
                    "description": description,
                    "start_date": activity.start_date.isoformat() if activity.start_date else None,
                    "distance": activity.distance,
                    "review_reason": "Nom non standard sans mot-cle fiable",
                })

        return {
            "message": f"Analyse complete: {len(suggestions)} suggestion(s), {len(manual_review)} activite(s) a verifier",
            "total_activities": len(activities),
            "suggestions_count": len(suggestions),
            "manual_review_count": len(manual_review),
            "suggestions": suggestions,
            "manual_review": manual_review,
        }

    def apply_auto_corrections(self, session: Session, user_id: str, corrections: list) -> dict:
        """Applique les corrections d'activités proposées par auto_correct_activity_types."""
        applied = []
        failed = []

        for correction in corrections:
            try:
                activity_id = correction.get("activity_id")
                new_type = correction.get("suggested_type")

                # Valide les données
                if not activity_id or not new_type:
                    failed.append({"activity_id": activity_id, "reason": "Donnees invalides"})
                    continue

                # Applique la correction
                result = self.update_activity_type(session, user_id, activity_id, new_type)
                applied.append({
                    "activity_id": activity_id,
                    "new_type": new_type,
                    "success": True,
                })
                logger.info(f"Auto-correction appliquee: {activity_id} → {new_type}")
            except Exception as e:
                failed.append({
                    "activity_id": correction.get("activity_id"),
                    "reason": str(e),
                })
                logger.error(f"Erreur auto-correction {correction.get('activity_id')}: {str(e)}")

        return {
            "message": f"{len(applied)} correction(s) appliquee(s), {len(failed)} erreur(s)",
            "applied_count": len(applied),
            "failed_count": len(failed),
            "applied": applied,
            "failed": failed,
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
