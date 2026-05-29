"""
Service Live - logique de persistance et de diffusion des trackpoints.

Cette couche est volontairement source-agnostique : elle est appelee par
le worker LiveTrack (phase 1) ET par l'endpoint HTTP /live/ingest (phase 2
Connect IQ). Tout ce qui touche au format Garmin reste dans livetrack_worker.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import Session, select

from app.core.redis import get_redis_client
from app.domain.entities.live_session import (
    LiveSession,
    LiveSessionStatus,
    LiveTrackpoint,
)

logger = logging.getLogger(__name__)


# ---------- Pubsub channel naming ----------

def channel_name(session_id: UUID) -> str:
    """Nom du canal Redis pubsub pour une session."""
    return f"live:{session_id}"


# ---------- Ingest ----------

def ingest_points(
    session: Session,
    session_id: UUID,
    points: list[dict[str, Any]],
) -> int:
    """
    Insere les points dans livetrackpoint en idempotent (ON CONFLICT DO NOTHING
    sur (session_id, ts)) puis publie le batch sur Redis pubsub.

    Returns:
        Nombre de points effectivement inseres (peut etre < len(points) si
        certains existaient deja).
    """
    if not points:
        return 0

    rows = []
    for p in points:
        ts = p.get("ts")
        if ts is None:
            continue
        rows.append({
            "session_id": session_id,
            "ts": int(ts),
            "lat": p.get("lat"),
            "lng": p.get("lng"),
            "hr": p.get("hr"),
            "speed": p.get("speed"),
            "cadence": p.get("cadence"),
            "power": p.get("power"),
            "distance": p.get("distance"),
            "altitude": p.get("altitude"),
        })

    if not rows:
        return 0

    stmt = (
        pg_insert(LiveTrackpoint.__table__)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["session_id", "ts"])
    )
    result = session.exec(stmt)
    inserted = result.rowcount or 0

    # Update du last_point_at + started_at si premier point
    live_session = session.get(LiveSession, session_id)
    if live_session is not None:
        max_ts = max(r["ts"] for r in rows)
        last_point_at = datetime.utcfromtimestamp(max_ts)
        live_session.last_point_at = last_point_at
        if live_session.started_at is None:
            min_ts = min(r["ts"] for r in rows)
            live_session.started_at = datetime.utcfromtimestamp(min_ts)
        live_session.updated_at = datetime.utcnow()
        session.add(live_session)

    session.commit()

    # Publie SEULEMENT les points qu'on vient de toucher (le subscriber dedupe
    # cote front sur ts de toute facon). On envoie le batch original pour
    # eviter de recharger depuis la BDD.
    _publish_points(session_id, rows)

    return inserted


def mark_session_finished(
    session: Session,
    session_id: UUID,
    status: LiveSessionStatus = LiveSessionStatus.FINISHED,
) -> None:
    """Marque une session comme terminee et notifie les subscribers."""
    live_session = session.get(LiveSession, session_id)
    if live_session is None or live_session.status != LiveSessionStatus.ACTIVE.value:
        return
    live_session.status = status.value
    live_session.ended_at = datetime.utcnow()
    live_session.updated_at = datetime.utcnow()
    session.add(live_session)
    session.commit()

    try:
        client = get_redis_client()
        client.publish(
            channel_name(session_id),
            json.dumps({"type": "ended", "status": status.value}),
        )
    except Exception as exc:
        logger.warning(f"Publish ended failed for session {session_id}: {exc}")


def get_snapshot(session: Session, session_id: UUID) -> list[dict[str, Any]]:
    """Retourne tous les trackpoints d'une session, tries par ts croissant."""
    rows = session.exec(
        select(LiveTrackpoint)
        .where(LiveTrackpoint.session_id == session_id)
        .order_by(LiveTrackpoint.ts)
    ).all()
    return [_trackpoint_to_dict(r) for r in rows]


# ---------- Helpers ----------

def _publish_points(session_id: UUID, rows: list[dict[str, Any]]) -> None:
    """Publie un batch de points sur le canal Redis (best-effort)."""
    try:
        client = get_redis_client()
        payload = {
            "type": "points",
            "points": [
                {k: v for k, v in r.items() if k != "session_id"}
                for r in rows
            ],
        }
        client.publish(channel_name(session_id), json.dumps(payload, default=str))
    except Exception as exc:
        logger.warning(f"Publish points failed for session {session_id}: {exc}")


def _trackpoint_to_dict(p: LiveTrackpoint) -> dict[str, Any]:
    return {
        "ts": p.ts,
        "lat": p.lat,
        "lng": p.lng,
        "hr": p.hr,
        "speed": p.speed,
        "cadence": p.cadence,
        "power": p.power,
        "distance": p.distance,
        "altitude": p.altitude,
    }
