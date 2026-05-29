"""
Worker LiveTrack - scrape la page HTML SSR Garmin LiveTrack pour
recuperer les trackpoints en quasi temps reel et les pousse via
live_service.ingest_points().

Depuis fin 2024, Garmin a refait LiveTrack en Next.js avec :
- protection Cloudflare sur l'API JSON `/api/sessions/{sid}` (403)
- mais la page HTML elle-meme est publique et contient les trackpoints
  via Next.js Server Components, embedded dans des chunks
  `self.__next_f.push([1,"..."])` dans le DOM initial.

Le worker recharge la page toutes les 4s et extrait :
  - sessionStatus
  - trackPoints (array d'objets)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlmodel import Session, select

from app.core.database import engine
from app.domain.entities.live_session import (
    LiveSession,
    LiveSessionSource,
    LiveSessionStatus,
)
from app.domain.services import live_service

logger = logging.getLogger(__name__)

LIVETRACK_PAGE_BASE = "https://livetrack.garmin.com/session"
POLL_INTERVAL_S = 4
POLL_INTERVAL_ON_ERROR_S = 8
INACTIVITY_TIMEOUT_S = 60  # auto-stop si rien recu pendant ce delai
HTTP_TIMEOUT_S = 15.0
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Regex pour extraire les chunks de data Next.js RSC
_NEXT_PUSH_RE = re.compile(
    r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*?)"\]\)',
    re.DOTALL,
)


class LiveTrackPoller:
    """Singleton qui gere une asyncio.Task par session active."""

    def __init__(self):
        self._tasks: dict[UUID, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def start_session(
        self,
        session_id: UUID,
        garmin_session_id: str,
        garmin_token: str,
    ) -> None:
        """Lance la task de polling pour une session. Idempotent."""
        existing = self._tasks.get(session_id)
        if existing and not existing.done():
            return
        loop = asyncio.get_event_loop()
        task = loop.create_task(
            self._poll_loop(session_id, garmin_session_id, garmin_token),
            name=f"livetrack-poll-{session_id}",
        )
        self._tasks[session_id] = task
        logger.info(f"LiveTrack poll demarre pour session {session_id}")

    def stop_session(self, session_id: UUID) -> None:
        """Annule la task de polling pour une session."""
        task = self._tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"LiveTrack poll arrete pour session {session_id}")

    async def restart_active_sessions(self) -> None:
        """Au boot, reprend toutes les sessions LiveTrack ACTIVE en BDD."""
        try:
            with Session(engine) as db:
                rows = db.exec(
                    select(LiveSession).where(
                        LiveSession.source == LiveSessionSource.LIVETRACK.value,
                        LiveSession.status == LiveSessionStatus.ACTIVE.value,
                    )
                ).all()
            count = 0
            for sess in rows:
                if sess.garmin_session_id and sess.garmin_token:
                    self.start_session(sess.id, sess.garmin_session_id, sess.garmin_token)
                    count += 1
            if count:
                logger.info(f"LiveTrack : {count} session(s) reprise(s) au boot")
        except Exception:
            logger.exception("Echec de la reprise des sessions LiveTrack au boot")

    def shutdown(self) -> None:
        """Annule toutes les tasks en cours (au shutdown du backend)."""
        for sid, task in list(self._tasks.items()):
            if not task.done():
                task.cancel()
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Boucle de polling
    # ------------------------------------------------------------------

    async def _poll_loop(
        self,
        session_id: UUID,
        garmin_session_id: str,
        garmin_token: str,
    ) -> None:
        last_ts = 0
        last_received_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
                while True:
                    sleep_s = POLL_INTERVAL_S
                    try:
                        status, raw_points = await self._fetch_session_html_data(
                            client, garmin_session_id, garmin_token
                        )

                        new_points = [
                            p for p in (parse_garmin_trackpoint(rp) for rp in raw_points)
                            if p is not None and p["ts"] > last_ts
                        ]

                        if new_points:
                            await asyncio.to_thread(self._persist, session_id, new_points)
                            last_ts = max(p["ts"] for p in new_points)
                            last_received_at = time.monotonic()
                            logger.debug(
                                f"Session {session_id}: +{len(new_points)} pts (ts={last_ts})"
                            )

                        # Termine cote Garmin ?
                        if status in ("Finished", "Completed", "Expired"):
                            logger.info(f"Session {session_id} terminee cote Garmin ({status})")
                            await asyncio.to_thread(
                                self._mark_finished, session_id, LiveSessionStatus.FINISHED
                            )
                            return

                        # Inactivite trop longue => auto-stop
                        if time.monotonic() - last_received_at > INACTIVITY_TIMEOUT_S:
                            logger.info(
                                f"Session {session_id}: auto-stop apres "
                                f"{INACTIVITY_TIMEOUT_S}s sans point"
                            )
                            await asyncio.to_thread(
                                self._mark_finished, session_id, LiveSessionStatus.STOPPED
                            )
                            return

                    except httpx.HTTPError as exc:
                        logger.warning(f"Session {session_id} HTTP error: {exc}")
                        sleep_s = POLL_INTERVAL_ON_ERROR_S
                    except Exception:
                        logger.exception(f"Session {session_id} poll error")
                        sleep_s = POLL_INTERVAL_ON_ERROR_S

                    await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            logger.info(f"Session {session_id} polling cancelled")
            raise
        finally:
            self._tasks.pop(session_id, None)

    # ------------------------------------------------------------------
    # Helpers HTTP : on scrape la page HTML SSR plutot que l'API JSON
    # (qui est protegee par Cloudflare 403).
    # ------------------------------------------------------------------

    async def _fetch_session_html_data(
        self,
        client: httpx.AsyncClient,
        garmin_session_id: str,
        garmin_token: str,
    ) -> tuple[Optional[str], list[dict[str, Any]]]:
        """
        Recupere la page HTML SSR et extrait (sessionStatus, trackPoints).

        Returns:
            (status, trackpoints) ou (None, []) si erreur fatale.
            status est l'un de :
              - "InProgress" : session active
              - "Finished"   : terminee normalement
              - "Expired"    : URL non reconnue ou trop vieille
              - None         : erreur transitoire (a retry)
        """
        url = f"{LIVETRACK_PAGE_BASE}/{garmin_session_id}/token/{garmin_token}"
        r = await client.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        if r.status_code == 404:
            return "Expired", []
        r.raise_for_status()
        html = r.text

        combined = _decode_next_push_chunks(html)
        trackpoints = _extract_trackpoints_array(combined)

        # NOTE : pas de marqueur fiable dans le SSR pour distinguer "session
        # finie" de "session active". Les chaines SessionEndedPage /
        # InvalidSessionPage sont presentes dans le bundle React TOUJOURS
        # (composants 404 normaux). On laisse donc le timeout d'inactivite
        # du worker (60s sans nouveau point) decider de l'arret.
        # On ne signale "Expired" que si Garmin retourne explicitement 404
        # sur l'URL (token invalide / session purgee cote serveur).
        return "InProgress", trackpoints

    # ------------------------------------------------------------------
    # Helpers BDD (executes en thread car SQLModel/SQLAlchemy sont sync)
    # ------------------------------------------------------------------

    @staticmethod
    def _persist(session_id: UUID, points: list[dict[str, Any]]) -> None:
        with Session(engine) as db:
            live_service.ingest_points(db, session_id, points)

    @staticmethod
    def _mark_finished(session_id: UUID, status: LiveSessionStatus) -> None:
        with Session(engine) as db:
            live_service.mark_session_finished(db, session_id, status)


# ---------- Parsing du payload Garmin ----------

def parse_garmin_trackpoint(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Convertit un trackpoint LiveTrack Garmin (structure Next.js 2024+) en
    dict standard pour live_service.ingest_points().

    Structure observee (HTML SSR de livetrack.garmin.com/session/...) :
      {
        "dateTime": "2026-05-25T20:31:12.000Z",
        "reportedTime": "2026-05-25T20:31:22.442Z",
        "position": {"lat": 49.227, "lon": 4.040},
        "speed": 0.25,
        "altitude": 79.47,
        "speedMetersPerSec": 0.25,
        "heartRateBeatsPerMin": 93,
        "pointStatus": "MOVING",
        "cadenceCyclesPerMin": 0,
        "powerWatts": 250 ou "$undefined",
        "totalDistanceMeters": 1234 ou "$undefined",
      }
    Garde un fallback sur l'ancienne structure fitnessPointData (anciens
    devices ou modeles non encore migres).
    """
    if not isinstance(raw, dict):
        return None

    ts = _extract_ts(raw)
    if ts is None:
        return None

    # Fallback ancien format
    fpd = raw.get("fitnessPointData") or {}
    pos = raw.get("position") or {}

    lat = pos.get("lat") if isinstance(pos, dict) else None
    lng = pos.get("lon") if isinstance(pos, dict) else None
    if lat is None:
        lat = raw.get("lat") or raw.get("latitude")
    if lng is None:
        lng = raw.get("lng") or raw.get("lon") or raw.get("longitude")

    # Helper pour lire un champ : nouveau format > ancien format > "$undefined" -> None
    def pick(*keys):
        for k in keys:
            # Top level prioritaire (nouveau format Next.js)
            if k in raw:
                v = raw[k]
                if v == "$undefined" or v is None:
                    continue
                return v
            # Fallback fitnessPointData
            if k in fpd:
                v = fpd[k]
                if v == "$undefined" or v is None:
                    continue
                return v
        return None

    return {
        "ts": ts,
        "lat": _as_float(lat),
        "lng": _as_float(lng),
        "hr": _as_int(pick("heartRateBeatsPerMin", "heartRate", "hr")),
        "speed": _as_float(pick("speedMetersPerSec", "speed")),
        "cadence": _as_int(pick("cadenceCyclesPerMin", "cadence")),
        "power": _as_int(pick("powerWatts", "power")),
        "distance": _as_float(pick("totalDistanceMeters", "distanceMeters", "distance")),
        "altitude": _as_float(pick("altitude", "elevationMeters")),
    }


# ---------- Helpers SSR Next.js ----------

def _decode_next_push_chunks(html: str) -> str:
    """Extrait et concatene tous les chunks self.__next_f.push de la page."""
    chunks = _NEXT_PUSH_RE.findall(html)
    out = []
    for chunk in chunks:
        try:
            out.append(chunk.encode('utf-8').decode('unicode_escape', errors='replace'))
        except Exception:
            continue
    return "".join(out)


def _extract_trackpoints_array(combined: str) -> list[dict[str, Any]]:
    """
    Trouve et parse l'array JSON `"trackPoints":[...]` dans la string
    combined (chunks RSC concatenes). Retourne [] si introuvable.
    """
    needle = '"trackPoints":['
    idx = combined.find(needle)
    if idx < 0:
        return []
    start = idx + len('"trackPoints":')
    end = _find_matching_bracket(combined, start)
    if end <= start:
        return []
    raw_array = combined[start:end]
    try:
        result = json.loads(raw_array)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError as exc:
        logger.warning(f"trackPoints JSON parse error: {exc}")
    return []


def _find_matching_bracket(s: str, start: int) -> int:
    """
    Etant donne s[start] == '[', retourne l'index juste apres le ']' qui
    ferme cette ouverture, en respectant les strings JSON (avec escapes).
    """
    if start >= len(s) or s[start] != '[':
        return -1
    depth = 0
    in_str = False
    escape_next = False
    for i in range(start, len(s)):
        ch = s[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _extract_ts(raw: dict[str, Any]) -> Optional[int]:
    """Extrait un timestamp epoch (seconds) depuis plusieurs formats possibles."""
    dt = raw.get("dateTime") or raw.get("date") or raw.get("ts")
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        # Pourrait etre ms : on heuristique
        v = float(dt)
        return int(v / 1000) if v > 10**12 else int(v)
    if isinstance(dt, str):
        try:
            cleaned = dt.replace("Z", "+00:00")
            return int(datetime.fromisoformat(cleaned).timestamp())
        except ValueError:
            return None
    return None


def _as_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# Singleton
livetrack_poller = LiveTrackPoller()
