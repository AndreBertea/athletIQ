"""
Handler pour les evenements webhook Strava.
Traite les evenements activity.create, activity.update, activity.delete.
"""
import logging
from sqlmodel import Session, select
from uuid import UUID

from app.core.database import engine
from app.domain.entities.activity import Activity
from app.domain.entities.user import StravaAuth
from app.domain.services.strava_sync_service import strava_sync_service
from app.domain.services.auto_enrichment_service import auto_enrichment_service

logger = logging.getLogger(__name__)


def _get_user_id_by_strava_athlete(session: Session, owner_id: int) -> str | None:
    """Trouve le user_id a partir du strava_athlete_id (owner_id du webhook)."""
    strava_auth = session.exec(
        select(StravaAuth).where(StravaAuth.strava_athlete_id == owner_id)
    ).first()
    if not strava_auth:
        return None
    return str(strava_auth.user_id)


def _get_activity_by_strava_id(session: Session, strava_id: int) -> Activity | None:
    """Trouve une activite en DB par son strava_id."""
    return session.exec(
        select(Activity).where(Activity.strava_id == strava_id)
    ).first()


def handle_activity_create(owner_id: int, strava_activity_id: int) -> None:
    """Traite un evenement activity.create.

    Recupere l'activite depuis l'API Strava et la sauvegarde en DB.
    """
    with Session(engine) as session:
        user_id = _get_user_id_by_strava_athlete(session, owner_id)
        if not user_id:
            logger.warning(f"Webhook activity.create: owner_id={owner_id} non trouve en DB")
            return

        # Verifier que l'activite n'existe pas deja
        existing = _get_activity_by_strava_id(session, strava_activity_id)
        if existing:
            logger.info(f"Webhook activity.create: activite strava_id={strava_activity_id} deja en DB")
            return

        # Recuperer les tokens et l'activite depuis Strava
        try:
            access_token, _ = strava_sync_service.get_user_strava_tokens(session, user_id)
        except Exception as e:
            logger.error(f"Webhook activity.create: erreur tokens pour user={user_id}: {e}")
            return

        strava_data = strava_sync_service.fetch_single_activity(access_token, strava_activity_id)
        if not strava_data:
            logger.warning(f"Webhook activity.create: activite {strava_activity_id} introuvable sur Strava")
            return

        activity_create = strava_sync_service.convert_strava_activity(strava_data, user_id)
        activity = Activity(user_id=UUID(user_id), **activity_create.model_dump())
        session.add(activity)
        session.commit()
        logger.info(f"Webhook activity.create: activite strava_id={strava_activity_id} sauvegardee (id={activity.id})")

        # Ajouter automatiquement a la queue d'enrichissement
        try:
            added = auto_enrichment_service.scheduler.add_to_queue(
                session, activity.id, UUID(user_id), priority=0
            )
            if added:
                auto_enrichment_service.notify_new_items()
                logger.info(f"Webhook activity.create: activite {activity.id} ajoutee a la queue d'enrichissement")
        except Exception as e:
            logger.error(f"Webhook activity.create: erreur ajout queue enrichissement: {e}")


def handle_activity_update(owner_id: int, strava_activity_id: int) -> None:
    """Traite un evenement activity.update.

    Re-synchronise l'activite depuis Strava et met a jour les champs en DB.
    """
    with Session(engine) as session:
        user_id = _get_user_id_by_strava_athlete(session, owner_id)
        if not user_id:
            logger.warning(f"Webhook activity.update: owner_id={owner_id} non trouve en DB")
            return

        activity = _get_activity_by_strava_id(session, strava_activity_id)
        if not activity:
            logger.warning(f"Webhook activity.update: strava_id={strava_activity_id} non trouve en DB, tentative de creation")
            handle_activity_create(owner_id, strava_activity_id)
            return

        try:
            access_token, _ = strava_sync_service.get_user_strava_tokens(session, user_id)
        except Exception as e:
            logger.error(f"Webhook activity.update: erreur tokens pour user={user_id}: {e}")
            return

        strava_data = strava_sync_service.fetch_single_activity(access_token, strava_activity_id)
        if not strava_data:
            logger.warning(f"Webhook activity.update: activite {strava_activity_id} introuvable sur Strava")
            return

        updated = strava_sync_service.convert_strava_activity(strava_data, user_id)
        # Mettre a jour les champs de l'activite existante
        for field_name, value in updated.model_dump().items():
            if value is not None:
                setattr(activity, field_name, value)
        from datetime import datetime
        activity.updated_at = datetime.utcnow()
        session.commit()
        logger.info(f"Webhook activity.update: activite strava_id={strava_activity_id} mise a jour")


def handle_activity_delete(owner_id: int, strava_activity_id: int) -> None:
    """Traite un evenement activity.delete.

    Supprime l'activite de la DB.
    """
    with Session(engine) as session:
        activity = _get_activity_by_strava_id(session, strava_activity_id)
        if not activity:
            logger.info(f"Webhook activity.delete: strava_id={strava_activity_id} non trouve en DB (deja supprime?)")
            return

        session.delete(activity)
        session.commit()
        logger.info(f"Webhook activity.delete: activite strava_id={strava_activity_id} supprimee")


def process_webhook_event(event: dict) -> None:
    """Dispatche un evenement webhook Strava vers le handler approprie.

    Appele de maniere asynchrone (fire-and-forget) par l'endpoint POST webhook.
    """
    object_type = event.get("object_type")
    aspect_type = event.get("aspect_type")
    object_id = event.get("object_id")
    owner_id = event.get("owner_id")

    if object_type != "activity":
        logger.debug(f"Webhook: object_type={object_type} ignore (seul 'activity' est gere)")
        return

    if aspect_type == "create":
        handle_activity_create(owner_id, object_id)
    elif aspect_type == "update":
        handle_activity_update(owner_id, object_id)
    elif aspect_type == "delete":
        handle_activity_delete(owner_id, object_id)
    else:
        logger.warning(f"Webhook: aspect_type={aspect_type} inconnu pour activity")
