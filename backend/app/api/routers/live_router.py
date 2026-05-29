"""
Routes Live - suivi d'activites en temps reel.

Phase 1 : ingestion via worker LiveTrack qui poll les endpoints publics Garmin.
Phase 2 (a venir) : ingestion via POST /live/ingest depuis un data field Connect IQ.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlmodel import Session, select

from app.api.routers._shared import security
from app.auth.jwt import get_current_user_id
from app.core.database import get_session
from app.core.settings import get_settings
from app.domain.entities.live_session import (
    LiveSession,
    LiveSessionCreate,
    LiveSessionDetail,
    LiveSessionRead,
    LiveSessionSource,
    LiveSessionStatus,
    LiveTrackpointRead,
)
from app.domain.entities.coach_athlete import (
    CoachAthleteRelation,
    RelationStatus,
)
from app.domain.entities.user import User
from app.domain.services import live_service
from app.domain.services.livetrack_worker import livetrack_poller
from jose import JWTError, jwt as jose_jwt
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/live", tags=["live"])

# Format attendu : https://livetrack.garmin.com/session/{sessionId}/token/{token}
_LIVETRACK_URL_RE = re.compile(
    r"livetrack\.garmin\.com/session/(?P<sid>[^/?#]+)/token/(?P<tok>[^/?#]+)",
    re.IGNORECASE,
)


# ---------- REST ----------

@router.get("/ws-token")
async def get_ws_token(token=Depends(security)):
    """
    Retourne le JWT actuel pour usage en query param WebSocket.

    Workaround au fait que les navigateurs n'envoient PAS les cookies httpOnly
    SameSite=Lax sur les WS handshakes. Le frontend appelle cet endpoint via
    XHR (cookie envoye), recupere le token, puis ouvre le WS avec ?token=...
    """
    return {"token": token.credentials}


@router.post("/sessions", response_model=LiveSessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: LiveSessionCreate,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Cree une session LiveTrack a partir d'une URL Garmin et demarre le poll."""
    user_id = UUID(get_current_user_id(token.credentials))

    match = _LIVETRACK_URL_RE.search(payload.url)
    if not match:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "URL LiveTrack invalide. Format attendu : "
                "https://livetrack.garmin.com/session/{sessionId}/token/{token}"
            ),
        )
    garmin_session_id = match.group("sid")
    garmin_token = match.group("tok")

    # Evite les doublons : si une session ACTIVE existe deja pour ce couple
    # (user, garmin_session_id), on la retourne.
    existing = db.exec(
        select(LiveSession).where(
            LiveSession.user_id == user_id,
            LiveSession.garmin_session_id == garmin_session_id,
            LiveSession.status == LiveSessionStatus.ACTIVE.value,
        )
    ).first()
    if existing:
        return existing

    sess = LiveSession(
        user_id=user_id,
        source=LiveSessionSource.LIVETRACK.value,
        label=payload.label,
        status=LiveSessionStatus.ACTIVE.value,
        garmin_session_id=garmin_session_id,
        garmin_token=garmin_token,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    livetrack_poller.start_session(sess.id, garmin_session_id, garmin_token)
    return sess


@router.get("/sessions", response_model=list[LiveSessionRead])
def list_sessions(
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Liste les sessions live de l'utilisateur (les plus recentes d'abord)."""
    user_id = UUID(get_current_user_id(token.credentials))
    rows = db.exec(
        select(LiveSession)
        .where(LiveSession.user_id == user_id)
        .order_by(LiveSession.created_at.desc())
    ).all()
    return rows


class SharedSessionEntry(BaseModel):
    """Vue d'une session live d'un athlete pour la page Shared Live."""
    session: LiveSessionRead
    athlete_id: UUID
    athlete_full_name: str
    athlete_email: str


@router.get("/shared/active-sessions", response_model=list[SharedSessionEntry])
def list_shared_active_sessions(
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Toutes les sessions ACTIVE des athletes acceptes par le coach courant."""
    coach_id = UUID(get_current_user_id(token.credentials))
    # Athletes acceptes par moi en tant que coach
    accepted_athlete_ids = [
        rel.athlete_id
        for rel in db.exec(
            select(CoachAthleteRelation).where(
                CoachAthleteRelation.coach_id == coach_id,
                CoachAthleteRelation.status == RelationStatus.ACCEPTED.value,
                CoachAthleteRelation.athlete_id.is_not(None),
            )
        ).all()
        if rel.athlete_id is not None
    ]
    if not accepted_athlete_ids:
        return []

    sessions = db.exec(
        select(LiveSession).where(
            LiveSession.user_id.in_(accepted_athlete_ids),
            LiveSession.status == LiveSessionStatus.ACTIVE.value,
        )
    ).all()

    out: list[SharedSessionEntry] = []
    for sess in sessions:
        athlete = db.get(User, sess.user_id)
        out.append(
            SharedSessionEntry(
                session=LiveSessionRead.model_validate(sess, from_attributes=True),
                athlete_id=sess.user_id,
                athlete_full_name=athlete.full_name if athlete else "",
                athlete_email=athlete.email if athlete else "",
            )
        )
    return out


@router.get("/sessions/{session_id}", response_model=LiveSessionDetail)
def get_session_detail(
    session_id: UUID,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Detail d'une session avec tous ses trackpoints (snapshot).

    Auth : l'owner OU un coach accepte de l'athlete owner peut lire.
    """
    user_id = UUID(get_current_user_id(token.credentials))
    sess = db.get(LiveSession, session_id)
    if not sess or not _can_read_session(db, sess, user_id):
        raise HTTPException(status_code=404, detail="Session introuvable")

    points = live_service.get_snapshot(db, session_id)
    return LiveSessionDetail(
        **LiveSessionRead.model_validate(sess, from_attributes=True).model_dump(),
        points=[LiveTrackpointRead(**p) for p in points],
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: UUID,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Stoppe le poll et supprime la session (cascade sur les trackpoints)."""
    user_id = UUID(get_current_user_id(token.credentials))
    sess = db.get(LiveSession, session_id)
    if not sess or sess.user_id != user_id:
        raise HTTPException(status_code=404, detail="Session introuvable")

    livetrack_poller.stop_session(session_id)
    db.delete(sess)
    db.commit()


# ---------- WebSocket ----------

@router.websocket("/follow/{session_id}")
async def follow_session(
    websocket: WebSocket,
    session_id: UUID,
    token: Optional[str] = Query(default=None),
):
    """
    WebSocket : envoie un snapshot initial, puis stream chaque nouveau batch
    via Redis pubsub. Termine sur {"type": "ended"} quand la session se cloture.

    Auth :
      - token JWT via query param ?token=...
      - fallback sur cookie access_token (si meme domaine)
    """
    user_id = _ws_authenticate(token, websocket)
    if user_id is None:
        await websocket.close(code=4401)
        return

    # Charge la session + verifie permission (owner OU coach accepte)
    from app.core.database import engine
    with Session(engine) as db:
        sess = db.get(LiveSession, session_id)
        if not sess or not _can_read_session(db, sess, user_id):
            await websocket.close(code=4404)
            return
        snapshot = live_service.get_snapshot(db, session_id)
        session_payload = LiveSessionRead.model_validate(sess, from_attributes=True).model_dump(mode="json")
        is_finished = sess.status != LiveSessionStatus.ACTIVE.value
        finished_status = sess.status

    await websocket.accept()
    await websocket.send_json({
        "type": "snapshot",
        "session": session_payload,
        "points": snapshot,
    })

    if is_finished:
        await websocket.send_json({"type": "ended", "status": finished_status})
        await websocket.close()
        return

    settings = get_settings()
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = live_service.channel_name(session_id)
    await pubsub.subscribe(channel)

    # Une task qui consomme le pubsub, et on guette en parallele la deco WS
    async def pump():
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                await websocket.send_text(msg["data"])
            except Exception:
                return
            try:
                parsed = json.loads(msg["data"])
                if parsed.get("type") == "ended":
                    return
            except Exception:
                pass

    pump_task = asyncio.create_task(pump())
    try:
        while not pump_task.done():
            try:
                # On detecte la deco client via un receive() avec timeout court.
                # receive_text leve WebSocketDisconnect quand le client ferme.
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
    finally:
        pump_task.cancel()
        try:
            await pump_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            await pubsub.close()
        except Exception:
            pass
        try:
            await redis_client.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


# ---------- Helpers ----------

def _can_read_session(db: Session, sess: LiveSession, user_id: UUID) -> bool:
    """Owner direct OU coach accepte de l'athlete owner = autorise."""
    if sess.user_id == user_id:
        return True
    coach_rel = db.exec(
        select(CoachAthleteRelation).where(
            CoachAthleteRelation.coach_id == user_id,
            CoachAthleteRelation.athlete_id == sess.user_id,
            CoachAthleteRelation.status == RelationStatus.ACCEPTED.value,
        )
    ).first()
    return coach_rel is not None


def _ws_authenticate(token: Optional[str], websocket: WebSocket) -> Optional[UUID]:
    """Decode le JWT venant du query param ou du cookie. Retourne user_id ou None."""
    raw = token or websocket.cookies.get("access_token")
    if not raw:
        return None
    try:
        settings = get_settings()
        payload = jose_jwt.decode(
            raw, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        sub = payload.get("sub")
        if not sub:
            return None
        return UUID(sub)
    except (JWTError, ValueError):
        return None
