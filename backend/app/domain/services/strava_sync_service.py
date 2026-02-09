"""
Service de synchronisation des activités Strava
"""
import logging
import requests

logger = logging.getLogger(__name__)
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlmodel import Session, select
from fastapi import HTTPException, status
from uuid import UUID

from app.auth.strava_oauth import strava_oauth
from app.domain.entities.activity import Activity, ActivityCreate
from app.domain.entities.user import StravaAuth


class StravaSyncService:
    """Service de synchronisation des activités Strava"""
    
    def __init__(self):
        self.api_url = "https://www.strava.com/api/v3"
    
    def get_user_strava_tokens(self, session: Session, user_id: str) -> tuple[str, str]:
        """Récupère les tokens Strava d'un utilisateur"""
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        
        if not strava_auth:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Strava not connected"
            )
        
        # Vérifier si le token est expiré
        if strava_oauth.is_token_expired(strava_auth.expires_at):
            # Actualiser le token
            new_tokens = strava_oauth.refresh_access_token(strava_auth.refresh_token_encrypted)
            
            # Mettre à jour en base
            strava_auth.access_token_encrypted = strava_oauth.encrypt_token(new_tokens.access_token)
            strava_auth.refresh_token_encrypted = strava_oauth.encrypt_token(new_tokens.refresh_token)
            strava_auth.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
            strava_auth.updated_at = datetime.utcnow()
            session.commit()
            
            return new_tokens.access_token, strava_auth.strava_athlete_id
        
        # Token valide
        access_token = strava_oauth.decrypt_token(strava_auth.access_token_encrypted)
        return access_token, strava_auth.strava_athlete_id
    
    def fetch_single_activity(self, access_token: str, strava_activity_id: int) -> Optional[Dict[str, Any]]:
        """Recupere une activite Strava par son ID."""
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get(
                f"{self.api_url}/activities/{strava_activity_id}",
                headers=headers,
                timeout=30,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Erreur fetch activite Strava {strava_activity_id}: {e}")
            return None

    def fetch_strava_activities(self, access_token: str, after: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Récupère les activités Strava"""
        headers = {"Authorization": f"Bearer {access_token}"}
        
        params = {
            "per_page": 200,  # Maximum autorisé par Strava
            "page": 1
        }
        
        if after:
            params["after"] = int(after.timestamp())
        
        activities = []
        
        try:
            while True:
                response = requests.get(
                    f"{self.api_url}/athlete/activities",
                    headers=headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                
                page_activities = response.json()
                if not page_activities:
                    break
                
                activities.extend(page_activities)
                
                # Si moins de 200 activités, c'est la dernière page
                if len(page_activities) < 200:
                    break
                
                params["page"] += 1
                
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch Strava activities: {str(e)}"
            )
        
        return activities
    
    def convert_strava_activity(self, strava_activity: Dict[str, Any], user_id: str) -> ActivityCreate:
        """Convertit une activité Strava en format ActivityCreate"""
        from app.domain.entities.activity import ActivityType

        # 1. Mapper le type d'activité Strava vers ActivityType Enum
        raw_type = strava_activity.get("type", "Run")  # défaut Run
        raw_type_lower = raw_type.lower()
        if raw_type_lower in ["trail run", "trail_run", "trailrun"]:
            mapped_type = ActivityType.TRAIL_RUN
        elif raw_type_lower == "run":
            mapped_type = ActivityType.RUN
        elif raw_type_lower in ["ride", "mountain bike", "mountain_bike", "ebike ride", "ebike_ride"]:
            mapped_type = ActivityType.RIDE
        elif raw_type_lower == "swim":
            mapped_type = ActivityType.SWIM
        elif raw_type_lower == "walk":
            mapped_type = ActivityType.WALK
        else:
            # Par défaut, on mappe sur RUN; l'énum ne supporte que les valeurs listées
            mapped_type = ActivityType.RUN

        # 2. Champs principaux
        distance = strava_activity.get("distance", 0.0)  # mètres
        moving_time_sec = strava_activity.get("moving_time", 0)
        elapsed_time_sec = strava_activity.get("elapsed_time", moving_time_sec)

        average_speed = distance / moving_time_sec if moving_time_sec > 0 else None
        max_speed = strava_activity.get("max_speed")

        total_elev = strava_activity.get("total_elevation_gain", 0.0)

        start_date_str = strava_activity.get("start_date")
        start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00")) if start_date_str else datetime.utcnow()

        # Calculer l'allure moyenne (min/km)
        average_pace = None
        if distance > 0 and moving_time_sec > 0:
            distance_km = distance / 1000
            time_min = moving_time_sec / 60
            average_pace = time_min / distance_km

        # Données GPS du résumé
        strava_map = strava_activity.get("map", {})
        summary_polyline = strava_map.get("summary_polyline") if strava_map else None

        # start_date_local
        start_date_local_str = strava_activity.get("start_date_local")
        start_date_local = datetime.fromisoformat(start_date_local_str.replace("Z", "+00:00")) if start_date_local_str else None

        # Coordonnées
        start_latlng = strava_activity.get("start_latlng")
        end_latlng = strava_activity.get("end_latlng")

        return ActivityCreate(
            name=strava_activity.get("name", "Activité sans nom"),
            activity_type=mapped_type,
            start_date=start_date,
            distance=distance,
            moving_time=moving_time_sec,
            elapsed_time=elapsed_time_sec,
            total_elevation_gain=total_elev,
            average_speed=average_speed,
            max_speed=max_speed,
            average_heartrate=strava_activity.get("average_heartrate"),
            max_heartrate=strava_activity.get("max_heartrate"),
            average_cadence=strava_activity.get("average_cadence"),
            description=strava_activity.get("description"),
            strava_id=strava_activity.get("id"),
            average_pace=average_pace,
            calories=strava_activity.get("calories"),
            start_date_local=start_date_local,
            start_latlng=start_latlng,
            end_latlng=end_latlng,
            summary_polyline=summary_polyline,
            workout_type=strava_activity.get("workout_type"),
            trainer=strava_activity.get("trainer"),
            commute=strava_activity.get("commute"),
            manual=strava_activity.get("manual"),
            suffer_score=strava_activity.get("suffer_score"),
            average_watts=strava_activity.get("average_watts"),
            max_watts=strava_activity.get("max_watts"),
            weighted_average_watts=strava_activity.get("weighted_average_watts"),
            kilojoules=strava_activity.get("kilojoules"),
        )
    
    def sync_activities(self, session: Session, user_id: str, days_back: int = 30) -> Dict[str, Any]:
        """Synchronise les activités Strava d'un utilisateur"""
        try:
            # Récupérer les tokens
            access_token, athlete_id = self.get_user_strava_tokens(session, user_id)
            
            # Calculer la date de début (si days_back >= 9999, importer toutes les activités)
            after_date = None
            if days_back < 9999:
                after_date = datetime.utcnow() - timedelta(days=days_back)
            
            # Récupérer les activités Strava
            strava_activities = self.fetch_strava_activities(access_token, after_date)
            
            # Récupérer les activités déjà synchronisées
            existing_strava_ids = session.exec(
                select(Activity.strava_id).where(
                    Activity.user_id == UUID(user_id),
                    Activity.strava_id.is_not(None)
                )
            ).all()
            
            # Filtrer les nouvelles activités
            new_activities = []
            for strava_activity in strava_activities:
                strava_id = strava_activity.get("id")
                if strava_id not in existing_strava_ids:
                    activity_create = self.convert_strava_activity(strava_activity, user_id)
                    new_activities.append(activity_create)
            
            # Sauvegarder les nouvelles activités
            saved_count = 0
            for activity_create in new_activities:
                # Créer Activity en ajoutant user_id
                activity = Activity(
                    user_id=UUID(user_id),
                    **activity_create.model_dump()
                )
                session.add(activity)
                saved_count += 1
            
            session.commit()
            
            # Message adapté selon la période
            if days_back >= 9999:
                period_msg = "Import complet de toutes vos activités"
            else:
                period_msg = f"Import des {days_back} derniers jours"
            
            return {
                "message": f"{period_msg} terminé",
                "total_activities_fetched": len(strava_activities),
                "new_activities_saved": saved_count,
                "athlete_id": athlete_id,
                "period": "all" if days_back >= 9999 else f"{days_back}_days"
            }
            
        except Exception as e:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Sync failed: {str(e)}"
            )


# Instance globale
strava_sync_service = StravaSyncService() 