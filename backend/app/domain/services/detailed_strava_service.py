"""
Service de récupération des données détaillées Strava avec gestion des quotas
"""
import requests
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlmodel import Session, select
from fastapi import HTTPException, status
from uuid import UUID
import asyncio
import logging

from app.auth.strava_oauth import strava_oauth
from app.domain.entities.activity import Activity
from app.domain.entities.user import StravaAuth
from app.domain.services.redis_quota_manager import RedisQuotaManager


logger = logging.getLogger(__name__)


class StravaQuotaManager:
    """Gestionnaire des quotas API Strava"""
    
    def __init__(self):
        # Limites API Strava (par défaut)
        self.daily_limit = 1000  # requêtes par jour
        self.per_15min_limit = 100  # requêtes par tranche de 15 min
        
        # Compteurs (en production, utiliser Redis ou BDD)
        self.daily_count = 0
        self.per_15min_count = 0
        self.last_15min_reset = datetime.utcnow()
        self.last_daily_reset = datetime.utcnow().date()
    
    def check_and_wait_if_needed(self) -> bool:
        """Vérifie les quotas et attend si nécessaire"""
        now = datetime.utcnow()
        
        # Reset quotas si nécessaire
        if now.date() > self.last_daily_reset:
            self.daily_count = 0
            self.last_daily_reset = now.date()
        
        if (now - self.last_15min_reset).total_seconds() >= 900:  # 15 min
            self.per_15min_count = 0
            self.last_15min_reset = now
        
        # Vérifier les limites
        if self.daily_count >= self.daily_limit:
            logger.warning("Quota journalier Strava atteint")
            return False
        
        if self.per_15min_count >= self.per_15min_limit:
            # Attendre jusqu'à la prochaine fenêtre de 15 min
            wait_time = 900 - (now - self.last_15min_reset).total_seconds()
            if wait_time > 0:
                logger.info(f"Quota 15min atteint, attente de {wait_time:.0f}s")
                time.sleep(wait_time)
                self.per_15min_count = 0
                self.last_15min_reset = datetime.utcnow()
        
        return True
    
    def increment_usage(self):
        """Incrémente les compteurs d'usage"""
        self.daily_count += 1
        self.per_15min_count += 1
    
    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut des quotas"""
        return {
            "daily_used": self.daily_count,
            "daily_limit": self.daily_limit,
            "per_15min_used": self.per_15min_count,
            "per_15min_limit": self.per_15min_limit,
            "next_15min_reset": self.last_15min_reset + timedelta(minutes=15),
            "daily_reset": datetime.combine(self.last_daily_reset + timedelta(days=1), datetime.min.time())
        }


class DetailedStravaService:
    """Service pour récupérer les données détaillées Strava"""
    
    def __init__(self):
        self.api_url = "https://www.strava.com/api/v3"
        self.quota_manager = RedisQuotaManager()
    
    def get_user_access_token(self, session: Session, user_id: str) -> str:
        """Récupère le token d'accès Strava pour un utilisateur"""
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        
        if not strava_auth:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Strava not connected"
            )
        
        # Vérifier expiration et rafraîchir si nécessaire
        if strava_oauth.is_token_expired(strava_auth.expires_at):
            new_tokens = strava_oauth.refresh_access_token(strava_auth.refresh_token_encrypted)
            strava_auth.access_token_encrypted = strava_oauth.encrypt_token(new_tokens.access_token)
            strava_auth.refresh_token_encrypted = strava_oauth.encrypt_token(new_tokens.refresh_token)
            strava_auth.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
            session.commit()
            return new_tokens.access_token
        
        return strava_oauth.decrypt_token(strava_auth.access_token_encrypted)
    
    def fetch_activity_streams(self, access_token: str, strava_activity_id: int) -> Optional[Dict[str, Any]]:
        """Récupère les streams d'une activité (données temporelles détaillées)"""
        if not self.quota_manager.check_and_wait_if_needed():
            return None
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        # Types de streams à récupérer
        stream_types = [
            "time",           # Temps (secondes)
            "latlng",         # Coordonnées GPS
            "distance",       # Distance cumulée
            "altitude",       # Altitude
            "velocity_smooth", # Vitesse lissée
            "heartrate",      # Fréquence cardiaque
            "cadence",        # Cadence
            "watts",          # Puissance
            "temp",           # Température
            "moving",         # Indicateur de mouvement
            "grade_smooth"    # Pente lissée
        ]
        
        try:
            response = requests.get(
                f"{self.api_url}/activities/{strava_activity_id}/streams",
                headers=headers,
                params={
                    "keys": ",".join(stream_types),
                    "key_by_type": "true"
                },
                timeout=30
            )
            
            self.quota_manager.increment_usage()
            
            if response.status_code == 404:
                logger.info(f"Pas de streams pour l'activité {strava_activity_id}")
                return None

            if response.status_code == 429:
                logger.warning("Rate limit Strava atteint (429). Arrêt de l'enrichissement.")
                self.quota_manager.daily_count = self.quota_manager.daily_limit
                return None

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Erreur récupération streams {strava_activity_id}: {e}")
            return None
    
    def fetch_activity_laps(self, access_token: str, strava_activity_id: int) -> Optional[List[Dict[str, Any]]]:
        """Récupère les tours/segments d'une activité"""
        if not self.quota_manager.check_and_wait_if_needed():
            return None
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            response = requests.get(
                f"{self.api_url}/activities/{strava_activity_id}/laps",
                headers=headers,
                timeout=30
            )
            
            self.quota_manager.increment_usage()
            
            if response.status_code == 404:
                return None

            if response.status_code == 429:
                logger.warning("Rate limit Strava atteint (429).")
                self.quota_manager.daily_count = self.quota_manager.daily_limit
                return None

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Erreur récupération laps {strava_activity_id}: {e}")
            return None
    
    def fetch_activity_segments(self, access_token: str, strava_activity_id: int) -> Optional[List[Dict[str, Any]]]:
        """Récupère les efforts sur segments Strava"""
        if not self.quota_manager.check_and_wait_if_needed():
            return None
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            response = requests.get(
                f"{self.api_url}/activities/{strava_activity_id}/segment_efforts",
                headers=headers,
                timeout=30
            )
            
            self.quota_manager.increment_usage()
            
            if response.status_code == 404:
                return None

            if response.status_code == 429:
                logger.warning("Rate limit Strava atteint (429).")
                self.quota_manager.daily_count = self.quota_manager.daily_limit
                return None

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Erreur récupération segments {strava_activity_id}: {e}")
            return None
    
    def fetch_activity_detail(self, access_token: str, strava_activity_id: int) -> Optional[Dict[str, Any]]:
        """Récupère le détail complet d'une activité (pour le polyline, etc.)"""
        if not self.quota_manager.check_and_wait_if_needed():
            return None

        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = requests.get(
                f"{self.api_url}/activities/{strava_activity_id}",
                headers=headers,
                timeout=30
            )

            self.quota_manager.increment_usage()

            if response.status_code == 404:
                return None
            if response.status_code == 429:
                logger.warning("Rate limit Strava atteint (429).")
                self.quota_manager.daily_count = self.quota_manager.daily_limit
                return None

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"Erreur récupération détail activité {strava_activity_id}: {e}")
            return None

    def enrich_activity_with_details(
        self, 
        session: Session, 
        user_id: str, 
        activity: Activity
    ) -> bool:
        """Enrichit une activité avec ses données détaillées"""
        if not activity.strava_id:
            logger.warning(f"Activité {activity.id} sans strava_id")
            return False
        
        # Vérifier si les données sont déjà présentes
        if activity.streams_data and activity.laps_data:
            logger.info(f"Activité {activity.id} déjà enrichie")
            return True
        
        try:
            access_token = self.get_user_access_token(session, user_id)
            
            # Récupérer les streams
            streams = self.fetch_activity_streams(access_token, activity.strava_id)
            
            # Récupérer les laps
            laps = self.fetch_activity_laps(access_token, activity.strava_id)
            
            # Récupérer les segments (optionnel)
            segments = self.fetch_activity_segments(access_token, activity.strava_id)
            
            # Mettre à jour l'activité
            if streams:
                activity.streams_data = streams
            
            if laps:
                activity.laps_data = laps
            
            # Ajouter les segments dans streams_data si disponibles
            if segments and streams:
                activity.streams_data["segment_efforts"] = segments
            elif segments:
                activity.streams_data = {"segment_efforts": segments}

            # Récupérer le détail pour le polyline complet
            detail = self.fetch_activity_detail(access_token, activity.strava_id)
            if detail:
                strava_map = detail.get("map", {})
                if strava_map:
                    polyline_full = strava_map.get("polyline")
                    if polyline_full:
                        activity.polyline = polyline_full
                    if not activity.summary_polyline:
                        summary = strava_map.get("summary_polyline")
                        if summary:
                            activity.summary_polyline = summary

            activity.updated_at = datetime.utcnow()
            session.commit()
            
            logger.info(f"Activité {activity.id} enrichie avec succès")
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Erreur enrichissement activité {activity.id}: {e}")
            return False
    
    def batch_enrich_activities(
        self, 
        session: Session, 
        user_id: str, 
        max_activities: int = 10
    ) -> Dict[str, Any]:
        """Enrichit un lot d'activités avec leurs données détaillées"""
        # Récupérer les activités sans données détaillées
        activities_to_enrich = session.exec(
            select(Activity)
            .where(
                Activity.user_id == UUID(user_id),
                Activity.strava_id.is_not(None),
                Activity.streams_data.is_(None)
            )
            .order_by(Activity.start_date.desc())
            .limit(max_activities)
        ).all()
        
        if not activities_to_enrich:
            return {
                "message": "Aucune activité à enrichir",
                "enriched_count": 0,
                "failed_count": 0,
                "quota_status": self.quota_manager.get_status()
            }
        
        enriched_count = 0
        failed_count = 0
        
        for activity in activities_to_enrich:
            # Vérifier le quota avant chaque activité
            if self.quota_manager.daily_count >= self.quota_manager.daily_limit:
                logger.warning("Quota journalier Strava atteint, arrêt de l'enrichissement. Réessayez demain.")
                break

            if self.enrich_activity_with_details(session, user_id, activity):
                enriched_count += 1
            else:
                failed_count += 1

            # Petit délai pour éviter de surcharger l'API
            time.sleep(0.5)
        
        return {
            "message": f"Enrichissement terminé: {enriched_count} réussies, {failed_count} échouées",
            "enriched_count": enriched_count,
            "failed_count": failed_count,
            "quota_status": self.quota_manager.get_status()
        }


# Instance globale
detailed_strava_service = DetailedStravaService() 