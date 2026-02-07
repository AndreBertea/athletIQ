"""
Service meteo — Enrichissement des activites via Open-Meteo API.
Tache 2.2.1 : extraire lat/lon du 1er point GPS, appeler Open-Meteo, trouver heure la plus proche.
Inclut 2.2.2 (Historical vs Forecast), 2.2.3 (delai 100ms), 2.2.4 (fetch/enrich/is_fetched).
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlmodel import Session, select

from app.domain.entities.activity import Activity
from app.domain.entities.activity_weather import ActivityWeather

logger = logging.getLogger(__name__)

# Open-Meteo : Historical si activite > 5 jours, Forecast sinon (tache 2.2.2)
HISTORICAL_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Variables horaires demandees
HOURLY_PARAMS = (
    "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,"
    "surface_pressure,precipitation,cloud_cover,weather_code"
)

# Delai entre appels (tache 2.2.3)
REQUEST_DELAY_S = 0.1

# Seuil pour choisir Historical vs Forecast (jours)
HISTORICAL_THRESHOLD_DAYS = 5


def _parse_streams(activity: Activity) -> Optional[Dict[str, Any]]:
    """Parse streams_data en gerant le bug 'null' string."""
    raw = activity.streams_data
    if raw is None:
        return None
    if isinstance(raw, str):
        if raw.strip().lower() == "null":
            return None
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    return raw


def _extract_first_gps(streams: Dict[str, Any]) -> Optional[tuple[float, float]]:
    """Extrait lat/lon du premier point GPS valide dans streams_data."""
    latlng = streams.get("latlng")
    if latlng is None:
        return None
    data = latlng.get("data") if isinstance(latlng, dict) else latlng if isinstance(latlng, list) else None
    if not data:
        return None
    for point in data:
        if isinstance(point, (list, tuple)) and len(point) == 2:
            lat, lon = point[0], point[1]
            if lat is not None and lon is not None:
                return (float(lat), float(lon))
    return None


def _find_closest_hour_index(hours: List[str], target: datetime) -> int:
    """Trouve l'index de l'heure la plus proche du start_date dans la liste ISO."""
    best_idx = 0
    best_diff = float("inf")
    for i, h in enumerate(hours):
        try:
            dt = datetime.fromisoformat(h)
        except ValueError:
            continue
        diff = abs((dt - target.replace(tzinfo=None)).total_seconds())
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return best_idx


def _build_weather_from_response(
    data: Dict[str, Any],
    activity: Activity,
) -> Optional[ActivityWeather]:
    """Construit un ActivityWeather a partir de la reponse Open-Meteo."""
    hourly = data.get("hourly")
    if not hourly:
        return None

    hours = hourly.get("time", [])
    if not hours:
        return None

    idx = _find_closest_hour_index(hours, activity.start_date)

    def _get(key: str) -> Optional[float]:
        values = hourly.get(key, [])
        if idx < len(values):
            return values[idx]
        return None

    return ActivityWeather(
        activity_id=activity.id,
        temperature_c=_get("temperature_2m"),
        humidity_pct=_get("relative_humidity_2m"),
        wind_speed_kmh=_get("wind_speed_10m"),
        wind_direction_deg=_get("wind_direction_10m"),
        pressure_hpa=_get("surface_pressure"),
        precipitation_mm=_get("precipitation"),
        cloud_cover_pct=_get("cloud_cover"),
        weather_code=int(_get("weather_code")) if _get("weather_code") is not None else None,
    )


async def _call_open_meteo(
    lat: float,
    lon: float,
    date: datetime,
    client: httpx.AsyncClient,
) -> Optional[Dict[str, Any]]:
    """Appelle Open-Meteo (Historical ou Forecast selon l'age de l'activite)."""
    now = datetime.now(timezone.utc)
    activity_date_aware = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    days_ago = (now - activity_date_aware).days

    date_str = date.strftime("%Y-%m-%d")

    if days_ago > HISTORICAL_THRESHOLD_DAYS:
        base_url = HISTORICAL_BASE_URL
    else:
        base_url = FORECAST_BASE_URL

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date_str,
        "end_date": date_str,
        "hourly": HOURLY_PARAMS,
        "timezone": "UTC",
    }

    try:
        resp = await client.get(base_url, params=params, timeout=15.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning(f"Open-Meteo HTTP {e.response.status_code} pour ({lat},{lon}) {date_str}")
        return None
    except httpx.RequestError as e:
        logger.warning(f"Open-Meteo erreur reseau pour ({lat},{lon}) {date_str}: {e}")
        return None


async def fetch_weather_for_activity(
    session: Session,
    activity: Activity,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """Recupere la meteo pour une activite et la stocke en base.

    Retourne True si la meteo a ete fetched et stockee, False sinon.
    """
    # Deja fetched ?
    if is_weather_fetched(session, activity.id):
        return True

    streams = _parse_streams(activity)
    if streams is None:
        logger.info(f"Activite {activity.id}: pas de streams_data, skip meteo")
        return False

    gps = _extract_first_gps(streams)
    if gps is None:
        logger.info(f"Activite {activity.id}: pas de GPS dans streams, skip meteo")
        return False

    lat, lon = gps

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient()

    try:
        data = await _call_open_meteo(lat, lon, activity.start_date, client)
        if data is None:
            return False

        weather = _build_weather_from_response(data, activity)
        if weather is None:
            logger.warning(f"Activite {activity.id}: reponse Open-Meteo vide ou invalide")
            return False

        session.add(weather)
        session.commit()
        logger.info(f"Activite {activity.id}: meteo stockee ({weather.temperature_c}°C)")
        return True
    finally:
        if owns_client:
            await client.aclose()


async def enrich_all_weather(
    session: Session,
    user_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Enrichit toutes les activites avec GPS pas encore enrichies en meteo.

    Retourne un resume {processed, skipped, errors}.
    """
    query = select(Activity).where(Activity.streams_data.is_not(None))
    if user_id:
        query = query.where(Activity.user_id == user_id)

    activities = session.exec(query).all()

    processed = 0
    skipped = 0
    errors = 0

    async with httpx.AsyncClient() as client:
        for activity in activities:
            if is_weather_fetched(session, activity.id):
                skipped += 1
                continue
            try:
                ok = await fetch_weather_for_activity(session, activity, client)
                if ok:
                    processed += 1
                else:
                    skipped += 1
                # Delai entre appels (tache 2.2.3)
                await asyncio.sleep(REQUEST_DELAY_S)
            except Exception as e:
                logger.error(f"Erreur meteo activite {activity.id}: {e}")
                errors += 1

    return {"processed": processed, "skipped": skipped, "errors": errors}


def is_weather_fetched(session: Session, activity_id: UUID) -> bool:
    """Verifie si la meteo a deja ete recuperee pour cette activite."""
    result = session.exec(
        select(ActivityWeather).where(ActivityWeather.activity_id == activity_id).limit(1)
    ).first()
    return result is not None
