"""
Service d'enrichissement automatique des activites avec scheduler round-robin.
Garantit une repartition equitable des quotas API Strava entre les utilisateurs.

Le worker background tourne en continu (asyncio.Task) et depile la queue
en respectant les quotas Strava (via RedisQuotaManager).
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from uuid import UUID

from app.core.database import get_session
from app.domain.entities.activity import Activity
from app.domain.entities.enrichment_queue import EnrichmentQueue, EnrichmentStatus
from app.domain.services.detailed_strava_service import detailed_strava_service
from app.domain.services.round_robin_scheduler import RoundRobinScheduler
from app.domain.services.segmentation_service import segment_activity
from app.domain.services.weather_service import fetch_weather_for_activity


logger = logging.getLogger(__name__)

# Intervalle entre les cycles quand la queue est active (secondes)
WORKER_INTERVAL = 30
# Intervalle quand la queue est vide — attend un signal ou ce timeout (secondes)
WORKER_IDLE_TIMEOUT = 300
# Pause quand les quotas 15min sont atteints (secondes)
QUOTA_15MIN_WAIT = 60
# Pause apres une erreur inattendue (secondes)
ERROR_WAIT = 30


class AutoEnrichmentService:
    """Service d'enrichissement automatique en arriere-plan avec round-robin."""

    def __init__(self):
        self.scheduler = RoundRobinScheduler()
        self.is_running = False
        self.batch_size = 5
        self._task: Optional[asyncio.Task] = None
        self._wake_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Lifecycle du worker
    # ------------------------------------------------------------------

    def start_worker(self) -> None:
        """Demarre le worker background comme asyncio.Task.

        Idempotent : si le worker tourne deja, ne fait rien.
        """
        if self._task and not self._task.done():
            return
        self._task = asyncio.get_event_loop().create_task(self._run_loop())
        logger.info("Worker d'enrichissement demarre")

    def stop_worker(self) -> None:
        """Arrete le worker background proprement."""
        self.is_running = False
        self._wake_event.set()  # Reveiller pour sortir immediatement
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Worker d'enrichissement arrete")

    def notify_new_items(self) -> None:
        """Reveille le worker quand de nouveaux items sont ajoutes a la queue."""
        self._wake_event.set()

    # ------------------------------------------------------------------
    # Boucle principale du worker
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        """Boucle principale du worker background."""
        self.is_running = True
        logger.info("Demarrage de la boucle d'enrichissement (round-robin)")

        while self.is_running:
            try:
                had_work = await self._process_queue_batch()

                # Si on a traite des items, re-boucler rapidement
                # Sinon, attendre un signal ou le timeout idle
                if had_work:
                    await asyncio.sleep(WORKER_INTERVAL)
                else:
                    self._wake_event.clear()
                    try:
                        await asyncio.wait_for(
                            self._wake_event.wait(),
                            timeout=WORKER_IDLE_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        pass  # Timeout idle, on re-verifie la queue

            except asyncio.CancelledError:
                logger.info("Worker d'enrichissement annule")
                break
            except Exception as e:
                logger.error(f"Erreur dans le worker d'enrichissement: {e}")
                await asyncio.sleep(ERROR_WAIT)

        self.is_running = False
        logger.info("Boucle d'enrichissement terminee")

    # ------------------------------------------------------------------
    # Traitement d'un batch
    # ------------------------------------------------------------------

    async def _process_queue_batch(self) -> bool:
        """Traite un lot d'activites via le scheduler round-robin.

        Retourne True si au moins un item a ete traite, False sinon.
        """
        quota = detailed_strava_service.quota_manager

        # Verifier le quota journalier (non-bloquant)
        if quota.daily_count >= quota.daily_limit:
            logger.warning("Quota journalier Strava atteint, pas de traitement")
            return False

        # Verifier le quota 15min (non-bloquant, on attend au prochain cycle)
        if quota.per_15min_count >= quota.per_15min_limit:
            logger.info(f"Quota 15min atteint, attente de {QUOTA_15MIN_WAIT}s")
            await asyncio.sleep(QUOTA_15MIN_WAIT)
            return False

        session = next(get_session())
        try:
            pending = self.scheduler.get_pending_count(session)
            if pending == 0:
                return False

            batch = self.scheduler.get_next_batch(session, self.batch_size)
            if not batch:
                return False

            processed_count = 0
            for activity_id, user_id in batch:
                # Re-verifier les quotas avant chaque enrichissement (3 appels API)
                if quota.daily_count >= quota.daily_limit:
                    logger.warning("Quota journalier atteint en cours de batch, arret")
                    break
                if quota.per_15min_count >= quota.per_15min_limit:
                    logger.info("Quota 15min atteint en cours de batch, arret")
                    break

                try:
                    success = await self._enrich_single_activity(activity_id, user_id)
                    if success:
                        processed_count += 1
                        self.scheduler.mark_completed(session, activity_id)
                        logger.info(f"Activite {activity_id} enrichie (user={user_id})")
                    else:
                        self.scheduler.mark_failed(session, activity_id, "enrichment returned false")

                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Erreur enrichissement activite {activity_id}: {e}")
                    self.scheduler.mark_failed(session, activity_id, str(e))

            if processed_count > 0:
                logger.info(f"Lot termine: {processed_count}/{len(batch)} activites enrichies (round-robin)")

            return processed_count > 0
        finally:
            session.close()

    # Compatibilite : ancienne methode publique
    async def start_background_enrichment(self):
        """Demarre l'enrichissement — delegue au worker."""
        self.start_worker()

    def stop_background_enrichment(self):
        """Arrete l'enrichissement — delegue au worker."""
        self.stop_worker()

    async def _enrich_single_activity(self, activity_id: str, user_id: str) -> bool:
        """Enrichit une activite specifique."""
        session = next(get_session())
        try:
            activity = session.exec(
                select(Activity).where(
                    Activity.id == UUID(activity_id),
                    Activity.user_id == UUID(user_id)
                )
            ).first()

            if not activity:
                logger.warning(f"Activite {activity_id} non trouvee")
                return False

            if activity.streams_data:
                logger.info(f"Activite {activity_id} deja enrichie")
                return True

            success = detailed_strava_service.enrich_activity_with_details(session, user_id, activity)

            if success:
                try:
                    segment_count = segment_activity(session, activity)
                    if segment_count > 0:
                        logger.info(f"Activite {activity_id}: {segment_count} segments crees apres enrichissement")
                except Exception as e:
                    logger.warning(f"Segmentation echouee pour activite {activity_id} (non-bloquant): {e}")

                try:
                    weather_ok = await fetch_weather_for_activity(session, activity)
                    if weather_ok:
                        logger.info(f"Activite {activity_id}: meteo enrichie apres segmentation")
                except Exception as e:
                    logger.warning(f"Meteo echouee pour activite {activity_id} (non-bloquant): {e}")

            return success
        finally:
            session.close()

    def add_user_activities_to_queue(self, user_id: str, priority: int = 0):
        """Ajoute toutes les activites non-enrichies d'un utilisateur a la queue."""
        session = next(get_session())
        try:
            activities = session.exec(
                select(Activity).where(
                    Activity.user_id == UUID(user_id),
                    Activity.strava_id.is_not(None),
                    Activity.streams_data.is_(None)
                ).order_by(Activity.start_date.desc())
            ).all()

            added_count = 0
            for activity in activities:
                if self.scheduler.add_to_queue(session, activity.id, UUID(user_id), priority):
                    added_count += 1

            if added_count > 0:
                self.start_worker()
                self.notify_new_items()

            logger.info(f"{added_count} activites ajoutees a la queue pour l'utilisateur {user_id}")
            return added_count
        finally:
            session.close()

    def prioritize_activity(self, activity_id: str, user_id: str) -> bool:
        """Met une activite en haute priorite (priority=-1 = avant les priorites normales)."""
        session = next(get_session())
        try:
            # Verifier si deja dans la queue
            existing = session.exec(
                select(EnrichmentQueue).where(
                    EnrichmentQueue.activity_id == UUID(activity_id),
                    EnrichmentQueue.status.in_([EnrichmentStatus.PENDING, EnrichmentStatus.IN_PROGRESS])
                )
            ).first()

            if existing:
                existing.priority = -1
                existing.updated_at = datetime.utcnow()
                session.add(existing)
                session.commit()
                self.notify_new_items()
                return True

            added = self.scheduler.add_to_queue(session, UUID(activity_id), UUID(user_id), priority=-1)
            if added:
                self.start_worker()
                self.notify_new_items()
            return added
        finally:
            session.close()

    def get_queue_status(self) -> Dict[str, Any]:
        """Retourne le statut de la queue."""
        session = next(get_session())
        try:
            status = self.scheduler.get_queue_status(session)
            status["is_running"] = self.is_running
            status["batch_size"] = self.batch_size
            return status
        finally:
            session.close()

    def get_user_queue_position(self, user_id: str) -> Dict[str, Any]:
        """Retourne la position d'un utilisateur dans la queue."""
        session = next(get_session())
        try:
            return self.scheduler.get_user_queue_position(session, UUID(user_id))
        finally:
            session.close()

    def get_user_queue_position_with_status(self, user_id: str) -> Dict[str, Any]:
        """Retourne la position de l'utilisateur avec le statut global de la queue."""
        position = self.get_user_queue_position(user_id)
        position["queue_status"] = self.get_queue_status()
        return position

    def start_enrichment_for_user(self, user_id: str) -> Dict[str, Any]:
        """Ajoute les activites non-enrichies a la queue et retourne le resultat complet."""
        added_count = self.add_user_activities_to_queue(user_id)
        return {
            "message": "Enrichissement automatique demarre",
            "activities_added_to_queue": added_count,
            "queue_status": self.get_queue_status(),
        }


# Instance globale
auto_enrichment_service = AutoEnrichmentService()
