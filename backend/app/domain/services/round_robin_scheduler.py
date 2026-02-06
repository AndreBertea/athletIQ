"""
Scheduler round-robin pour l'enrichissement des activites Strava.
Chaque utilisateur a droit a N enrichissements par cycle, garantissant
une repartition equitable des quotas API entre les utilisateurs.
"""
import logging
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from sqlmodel import Session, select, col, or_
from sqlalchemy import func

from app.core.database import get_session
from app.domain.entities.enrichment_queue import EnrichmentQueue, EnrichmentStatus

logger = logging.getLogger(__name__)

# Nombre d'enrichissements par utilisateur par cycle
ITEMS_PER_USER_PER_CYCLE = 2


class RoundRobinScheduler:
    """Scheduler round-robin qui alterne entre les utilisateurs pour l'enrichissement."""

    def __init__(self, items_per_user: int = ITEMS_PER_USER_PER_CYCLE):
        self.items_per_user = items_per_user
        self._last_user_index = 0

    def add_to_queue(self, session: Session, activity_id: UUID, user_id: UUID, priority: int = 0) -> bool:
        """Ajoute une activite a la queue d'enrichissement. Retourne False si deja presente."""
        existing = session.exec(
            select(EnrichmentQueue).where(
                EnrichmentQueue.activity_id == activity_id,
                EnrichmentQueue.status.in_([EnrichmentStatus.PENDING, EnrichmentStatus.IN_PROGRESS])
            )
        ).first()
        if existing:
            return False

        item = EnrichmentQueue(
            activity_id=activity_id,
            user_id=user_id,
            priority=priority,
            status=EnrichmentStatus.PENDING,
        )
        session.add(item)
        session.commit()
        logger.info(f"Activite {activity_id} ajoutee a la queue (user={user_id}, priority={priority})")
        return True

    def get_next_batch(self, session: Session, batch_size: int) -> List[Tuple[str, str]]:
        """
        Retourne le prochain lot d'activites a enrichir en round-robin.
        Alterne entre les utilisateurs, chacun ayant droit a `items_per_user` items par cycle.
        Retourne une liste de (activity_id, user_id).
        """
        now = datetime.utcnow()
        # Filtre : PENDING et pret pour traitement (pas de backoff en cours)
        ready_filter = [
            EnrichmentQueue.status == EnrichmentStatus.PENDING,
            or_(
                EnrichmentQueue.next_retry_at.is_(None),
                EnrichmentQueue.next_retry_at <= now,
            ),
        ]

        # Recuperer les user_ids distincts ayant des items PENDING prets, tries par priorite puis anciennete
        user_ids = session.exec(
            select(EnrichmentQueue.user_id)
            .where(*ready_filter)
            .group_by(EnrichmentQueue.user_id)
            .order_by(func.min(EnrichmentQueue.priority), func.min(EnrichmentQueue.created_at))
        ).all()

        if not user_ids:
            return []

        # Rotation : commencer apres le dernier utilisateur servi
        user_ids = list(user_ids)
        if self._last_user_index >= len(user_ids):
            self._last_user_index = 0
        rotated = user_ids[self._last_user_index:] + user_ids[:self._last_user_index]

        batch: List[Tuple[str, str]] = []
        users_served = 0

        for user_id in rotated:
            if len(batch) >= batch_size:
                break

            remaining = batch_size - len(batch)
            take = min(self.items_per_user, remaining)

            items = session.exec(
                select(EnrichmentQueue)
                .where(
                    EnrichmentQueue.user_id == user_id,
                    EnrichmentQueue.status == EnrichmentStatus.PENDING,
                    or_(
                        EnrichmentQueue.next_retry_at.is_(None),
                        EnrichmentQueue.next_retry_at <= now,
                    ),
                )
                .order_by(EnrichmentQueue.priority, EnrichmentQueue.created_at)
                .limit(take)
            ).all()

            for item in items:
                item.status = EnrichmentStatus.IN_PROGRESS
                item.updated_at = datetime.utcnow()
                session.add(item)
                batch.append((str(item.activity_id), str(item.user_id)))

            users_served += 1

        if batch:
            session.commit()
            # Avancer le curseur pour le prochain cycle
            self._last_user_index = (self._last_user_index + users_served) % max(len(user_ids), 1)

        return batch

    def mark_completed(self, session: Session, activity_id: str) -> None:
        """Marque un item comme termine."""
        item = session.exec(
            select(EnrichmentQueue).where(
                EnrichmentQueue.activity_id == UUID(activity_id),
                EnrichmentQueue.status == EnrichmentStatus.IN_PROGRESS,
            )
        ).first()
        if item:
            item.status = EnrichmentStatus.COMPLETED
            item.updated_at = datetime.utcnow()
            session.add(item)
            session.commit()

    def mark_failed(self, session: Session, activity_id: str, error: str) -> None:
        """Marque un item comme echoue. Remet en PENDING avec backoff si tentatives < max_attempts."""
        item = session.exec(
            select(EnrichmentQueue).where(
                EnrichmentQueue.activity_id == UUID(activity_id),
                EnrichmentQueue.status == EnrichmentStatus.IN_PROGRESS,
            )
        ).first()
        if item:
            item.attempts += 1
            item.last_error = error
            item.updated_at = datetime.utcnow()

            if item.attempts < item.max_attempts:
                # Backoff exponentiel : 30s, 120s, 480s (30 * 2^(attempt-1) * 2)
                delay_seconds = 30 * (2 ** (item.attempts - 1))
                item.status = EnrichmentStatus.PENDING
                item.next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
                logger.info(
                    f"Activite {activity_id} echouee (tentative {item.attempts}/{item.max_attempts}), "
                    f"retry dans {delay_seconds}s"
                )
            else:
                item.status = EnrichmentStatus.FAILED
                item.next_retry_at = None
                logger.warning(
                    f"Activite {activity_id} echouee definitivement apres {item.attempts} tentatives: {error}"
                )

            session.add(item)
            session.commit()

    def get_queue_status(self, session: Session) -> Dict[str, Any]:
        """Retourne le statut de la queue."""
        pending = session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.status == EnrichmentStatus.PENDING
            )
        ).one()
        in_progress = session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.status == EnrichmentStatus.IN_PROGRESS
            )
        ).one()
        # Nombre d'utilisateurs en attente
        user_count = session.exec(
            select(func.count(func.distinct(EnrichmentQueue.user_id))).select_from(EnrichmentQueue).where(
                EnrichmentQueue.status == EnrichmentStatus.PENDING
            )
        ).one()

        return {
            "queue_size": pending,
            "processing_count": in_progress,
            "users_in_queue": user_count,
            "items_per_user_per_cycle": self.items_per_user,
        }

    def get_user_queue_position(self, session: Session, user_id: UUID) -> Dict[str, Any]:
        """Retourne la position d'un utilisateur dans la queue d'enrichissement."""
        # Items de cet utilisateur en attente
        user_pending = session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.user_id == user_id,
                EnrichmentQueue.status == EnrichmentStatus.PENDING,
            )
        ).one()

        # Items de cet utilisateur en cours de traitement
        user_in_progress = session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.user_id == user_id,
                EnrichmentQueue.status == EnrichmentStatus.IN_PROGRESS,
            )
        ).one()

        # Total des items PENDING avant cet utilisateur (priorite + anciennete)
        # = items d'autres utilisateurs qui seront traites avant les siens
        # On prend le created_at le plus ancien de cet utilisateur comme reference
        user_oldest = session.exec(
            select(func.min(EnrichmentQueue.created_at)).where(
                EnrichmentQueue.user_id == user_id,
                EnrichmentQueue.status == EnrichmentStatus.PENDING,
            )
        ).one()

        ahead_count = 0
        if user_oldest is not None:
            # Items d'autres utilisateurs avec priorite inferieure (= plus haute)
            # ou meme priorite mais plus anciens
            user_min_priority = session.exec(
                select(func.min(EnrichmentQueue.priority)).where(
                    EnrichmentQueue.user_id == user_id,
                    EnrichmentQueue.status == EnrichmentStatus.PENDING,
                )
            ).one()

            ahead_count = session.exec(
                select(func.count()).select_from(EnrichmentQueue).where(
                    EnrichmentQueue.user_id != user_id,
                    EnrichmentQueue.status == EnrichmentStatus.PENDING,
                    EnrichmentQueue.priority <= user_min_priority,
                )
            ).one()

        # Items termines/echoues de l'utilisateur (pour info)
        user_completed = session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.user_id == user_id,
                EnrichmentQueue.status == EnrichmentStatus.COMPLETED,
            )
        ).one()

        user_failed = session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.user_id == user_id,
                EnrichmentQueue.status == EnrichmentStatus.FAILED,
            )
        ).one()

        return {
            "user_pending": user_pending,
            "user_in_progress": user_in_progress,
            "user_completed": user_completed,
            "user_failed": user_failed,
            "ahead_in_queue": ahead_count,
            "estimated_position": ahead_count + 1 if user_pending > 0 else 0,
        }

    def get_pending_count(self, session: Session) -> int:
        """Retourne le nombre total d'items PENDING prets pour traitement."""
        now = datetime.utcnow()
        return session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.status == EnrichmentStatus.PENDING,
                or_(
                    EnrichmentQueue.next_retry_at.is_(None),
                    EnrichmentQueue.next_retry_at <= now,
                ),
            )
        ).one()

    def get_in_progress_count(self, session: Session) -> int:
        """Retourne le nombre d'items IN_PROGRESS."""
        return session.exec(
            select(func.count()).select_from(EnrichmentQueue).where(
                EnrichmentQueue.status == EnrichmentStatus.IN_PROGRESS
            )
        ).one()
