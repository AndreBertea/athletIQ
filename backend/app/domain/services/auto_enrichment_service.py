"""
Service d'enrichissement automatique des activités avec système de priorité
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from uuid import UUID

from app.core.database import get_session
from app.domain.entities.activity import Activity
from app.domain.services.detailed_strava_service import detailed_strava_service


logger = logging.getLogger(__name__)


class EnrichmentQueue:
    """Queue de priorité pour l'enrichissement des activités"""
    
    def __init__(self):
        self.priority_queue: List[tuple[int, str, str]] = []  # (priority, activity_id, user_id)
        self.processing: Dict[str, bool] = {}  # activity_id -> is_processing
    
    def add_activity(self, activity_id: str, user_id: str, priority: int = 5):
        """Ajoute une activité à la queue avec priorité (1=max priorité, 10=min priorité)"""
        # Éviter les doublons
        for p, aid, uid in self.priority_queue:
            if aid == activity_id:
                return False
        
        self.priority_queue.append((priority, activity_id, user_id))
        self.priority_queue.sort(key=lambda x: x[0])  # Trier par priorité
        logger.info(f"Activité {activity_id} ajoutée à la queue avec priorité {priority}")
        return True
    
    def get_next_activity(self) -> Optional[tuple[str, str]]:
        """Récupère la prochaine activité à traiter"""
        while self.priority_queue:
            priority, activity_id, user_id = self.priority_queue.pop(0)
            
            # Vérifier si pas déjà en cours de traitement
            if not self.processing.get(activity_id, False):
                self.processing[activity_id] = True
                return activity_id, user_id
        
        return None
    
    def mark_completed(self, activity_id: str):
        """Marque une activité comme terminée"""
        self.processing.pop(activity_id, None)
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Retourne le statut de la queue"""
        return {
            "queue_size": len(self.priority_queue),
            "processing_count": len(self.processing),
            "next_activities": [aid for _, aid, _ in self.priority_queue[:5]]
        }


class AutoEnrichmentService:
    """Service d'enrichissement automatique en arrière-plan"""
    
    def __init__(self):
        self.queue = EnrichmentQueue()
        self.is_running = False
        self.batch_size = 5  # Nombre d'activités à traiter par lot
    
    async def start_background_enrichment(self):
        """Démarre l'enrichissement en arrière-plan"""
        if self.is_running:
            return
        
        self.is_running = True
        logger.info("Démarrage de l'enrichissement automatique")
        
        while self.is_running:
            try:
                await self._process_queue_batch()
                # Attendre 5 minutes entre les lots pour respecter les quotas
                await asyncio.sleep(300)  # 5 minutes
            except Exception as e:
                logger.error(f"Erreur dans l'enrichissement automatique: {e}")
                await asyncio.sleep(60)  # 1 minute avant de réessayer
    
    def stop_background_enrichment(self):
        """Arrête l'enrichissement en arrière-plan"""
        self.is_running = False
        logger.info("Arrêt de l'enrichissement automatique")
    
    async def _process_queue_batch(self):
        """Traite un lot d'activités de la queue"""
        if not detailed_strava_service.quota_manager.check_and_wait_if_needed():
            logger.warning("Quotas API atteints, attente...")
            return
        
        # Vérifier s'il y a quelque chose à traiter
        if len(self.priority_queue) == 0 and len(self.processing) == 0:
            logger.info("🏁 Queue vide - arrêt automatique de l'enrichissement")
            self.stop_background_enrichment()
            return
        
        processed_count = 0
        
        for _ in range(self.batch_size):
            if processed_count >= self.batch_size:
                break
            
            next_activity = self.queue.get_next_activity()
            if not next_activity:
                break
            
            activity_id, user_id = next_activity
            
            try:
                # Enrichir l'activité
                success = await self._enrich_single_activity(activity_id, user_id)
                if success:
                    processed_count += 1
                    logger.info(f"Activité {activity_id} enrichie automatiquement")
                
                # Marquer comme terminé
                self.queue.mark_completed(activity_id)
                
                # Petit délai entre les activités
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Erreur enrichissement activité {activity_id}: {e}")
                self.queue.mark_completed(activity_id)
        
        if processed_count > 0:
            logger.info(f"Lot terminé: {processed_count} activités enrichies")
        
        # Vérifier à nouveau si la queue est vide après traitement
        if len(self.priority_queue) == 0 and len(self.processing) == 0:
            logger.info("🏁 Toutes les activités traitées - arrêt automatique")
            self.stop_background_enrichment()
    
    async def _enrich_single_activity(self, activity_id: str, user_id: str) -> bool:
        """Enrichit une activité spécifique"""
        session = next(get_session())
        
        try:
            # Récupérer l'activité
            activity = session.exec(
                select(Activity).where(
                    Activity.id == UUID(activity_id),
                    Activity.user_id == UUID(user_id)
                )
            ).first()
            
            if not activity:
                logger.warning(f"Activité {activity_id} non trouvée")
                return False
            
            # Vérifier si déjà enrichie
            if activity.streams_data:
                logger.info(f"Activité {activity_id} déjà enrichie")
                return True
            
            # Enrichir
            return detailed_strava_service.enrich_activity_with_details(session, user_id, activity)
            
        finally:
            session.close()
    
    def add_user_activities_to_queue(self, user_id: str, priority: int = 5):
        """Ajoute toutes les activités non-enrichies d'un utilisateur à la queue"""
        session = next(get_session())
        
        try:
            # Récupérer les activités non enrichies
            activities = session.exec(
                select(Activity).where(
                    Activity.user_id == UUID(user_id),
                    Activity.strava_id.is_not(None),
                    Activity.streams_data.is_(None)
                ).order_by(Activity.start_date.desc())
            ).all()
            
            added_count = 0
            for activity in activities:
                if self.queue.add_activity(str(activity.id), user_id, priority):
                    added_count += 1
            
            logger.info(f"{added_count} activités ajoutées à la queue pour l'utilisateur {user_id}")
            return added_count
            
        finally:
            session.close()
    
    def prioritize_activity(self, activity_id: str, user_id: str) -> bool:
        """Met une activité en haute priorité (priorité 1)"""
        return self.queue.add_activity(activity_id, user_id, priority=1)
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Retourne le statut de la queue"""
        return {
            **self.queue.get_queue_status(),
            "is_running": self.is_running,
            "batch_size": self.batch_size
        }


# Instance globale
auto_enrichment_service = AutoEnrichmentService() 