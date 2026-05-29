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
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.domain.entities.activity import Activity, ActivitySource
from app.domain.entities.activity_weather import ActivityWeather

logger = logging.getLogger(__name__)

# Open-Meteo : Historical si activite > 5 jours, Forecast sinon (tache 2.2.2)
HISTORICAL_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# Variables horaires demandees. Les colonnes simples gardent les metriques coeur,
# le snapshot JSON conserve les variables avancees pour analyses futures.
CORE_HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "surface_pressure",
    "precipitation",
    "cloud_cover",
    "weather_code",
)
EXTENDED_HOURLY_VARIABLES = (
    "apparent_temperature",
    "dew_point_2m",
    "rain",
    "showers",
    "snowfall",
    "pressure_msl",
    "cloud_cover_low",
    "cloud_cover_mid",
    "cloud_cover_high",
    "wind_gusts_10m",
    "vapour_pressure_deficit",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
)
HOURLY_VARIABLES = CORE_HOURLY_VARIABLES + EXTENDED_HOURLY_VARIABLES
HOURLY_PARAMS = ",".join(HOURLY_VARIABLES)

# Delai entre appels (tache 2.2.3)
REQUEST_DELAY_S = 0.3
REQUEST_TIMEOUT_S = 8.0
HISTORICAL_REQUEST_TIMEOUT_S = 30.0
DEFAULT_BATCH_SIZE = 25
DEFAULT_CONCURRENCY = 2
OPEN_METEO_MAX_ATTEMPTS = 2
OPEN_METEO_RATE_LIMIT_BACKOFF_S = 2.0
WEATHER_TIMELINE_INTERVAL_MIN = 10

# L'endpoint forecast Open-Meteo expose les observations recentes via past_days.
# Les endpoints archive/historical time outent parfois en local, donc on les garde
# uniquement pour l'historique plus ancien.
FORECAST_LOOKBACK_DAYS = 93
HISTORICAL_THRESHOLD_DAYS = FORECAST_LOOKBACK_DAYS

WEATHER_REQUEST_TEMPLATES = {
    "forecast_recent": {
        "name": "forecast_recent",
        "base_url": FORECAST_BASE_URL,
        "description": "Meteo recente via Forecast API avec past_days.",
        "max_past_days": FORECAST_LOOKBACK_DAYS,
        "hourly": list(HOURLY_VARIABLES),
    },
    "historical_archive": {
        "name": "historical_archive",
        "base_url": HISTORICAL_BASE_URL,
        "description": "Meteo historique via archive-api.open-meteo.com.",
        "hourly": list(HOURLY_VARIABLES),
    },
}


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


def _coerce_latlng(raw: Any) -> Optional[tuple[float, float]]:
    """Normalise une coordonnee [lat, lon] provenant de l'activite."""
    if raw is None:
        return None
    if isinstance(raw, str):
        if raw.strip().lower() in {"", "null", "[]"}:
            return None
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    if isinstance(raw, dict):
        lat = raw.get("lat") if "lat" in raw else raw.get("latitude")
        if "lon" in raw:
            lon = raw.get("lon")
        elif "lng" in raw:
            lon = raw.get("lng")
        else:
            lon = raw.get("longitude")
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        lat, lon = raw[0], raw[1]
    else:
        return None

    if lat is None or lon is None:
        return None

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None

    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        return None

    return (lat_f, lon_f)


def _extract_activity_gps(activity: Activity) -> Optional[tuple[float, float]]:
    """Trouve les coordonnees meteo les plus fiables pour une activite."""
    streams = _parse_streams(activity)
    if streams is not None:
        gps = _extract_first_gps(streams)
        if gps is not None:
            return gps

    for attr_name in ("start_latlng", "end_latlng"):
        gps = _coerce_latlng(getattr(activity, attr_name, None))
        if gps is not None:
            return gps

    return None


def _days_ago(date: datetime) -> int:
    now = datetime.now(timezone.utc)
    activity_date_aware = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
    return (now.date() - activity_date_aware.date()).days


def _is_forecast_api_supported(date: datetime) -> bool:
    days_ago = _days_ago(date)
    return 0 <= days_ago <= FORECAST_LOOKBACK_DAYS


def get_weather_request_templates() -> Dict[str, Any]:
    """Expose les templates de requete Open-Meteo utilises par le backend."""
    return WEATHER_REQUEST_TEMPLATES


def _build_open_meteo_request(
    lat: float,
    lon: float,
    date: datetime,
    duration_seconds: int = 0,
) -> tuple[str, Dict[str, Any], str]:
    """Construit l'URL, les parametres et le nom du template Open-Meteo."""
    days_ago = _days_ago(date)
    date_str = date.strftime("%Y-%m-%d")
    end_date = (date + timedelta(seconds=max(0, duration_seconds), hours=1)).strftime("%Y-%m-%d")

    if _is_forecast_api_supported(date):
        template_name = "forecast_recent"
    else:
        template_name = "historical_archive"

    template = WEATHER_REQUEST_TEMPLATES[template_name]
    params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(template["hourly"]),
        "timezone": "UTC",
    }

    if template_name == "forecast_recent":
        params["forecast_days"] = 1
        if days_ago > 0:
            params["past_days"] = min(days_ago, FORECAST_LOOKBACK_DAYS)
    else:
        params["start_date"] = date_str
        params["end_date"] = end_date

    return str(template["base_url"]), params, template_name


def _activity_duration_seconds(activity: Activity) -> int:
    """Retourne la duree exploitable pour construire la timeline meteo."""
    for attr_name in ("elapsed_time", "moving_time"):
        raw_value = getattr(activity, attr_name, None)
        if not isinstance(raw_value, (int, float)):
            continue
        value = int(raw_value)
        if value > 0:
            return value
    return 0


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


def _parse_hour_datetime(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _target_naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def _hour_datetimes(hours: List[str]) -> List[Optional[datetime]]:
    return [_parse_hour_datetime(str(value)) for value in hours]


def _interpolate_hourly_value(
    timestamps: List[Optional[datetime]],
    values: Any,
    target: datetime,
) -> Optional[float]:
    """Interpolation lineaire d'une variable horaire vers une heure cible."""
    if not isinstance(values, list):
        return None

    target_naive = _target_naive(target)
    points: List[tuple[datetime, float]] = []
    for timestamp, value in zip(timestamps, values):
        if timestamp is None or value is None:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        points.append((timestamp, numeric_value))

    if not points:
        return None

    points.sort(key=lambda item: item[0])
    if target_naive <= points[0][0]:
        return points[0][1]
    if target_naive >= points[-1][0]:
        return points[-1][1]

    for previous, current in zip(points, points[1:]):
        previous_time, previous_value = previous
        current_time, current_value = current
        if previous_time <= target_naive <= current_time:
            total_seconds = (current_time - previous_time).total_seconds()
            if total_seconds <= 0:
                return current_value
            weight = (target_naive - previous_time).total_seconds() / total_seconds
            return previous_value + weight * (current_value - previous_value)

    return points[-1][1]


def _nearest_hour_value(
    timestamps: List[Optional[datetime]],
    values: Any,
    target: datetime,
) -> Any:
    """Retourne la valeur de l'heure la plus proche pour les variables discretes."""
    if not isinstance(values, list):
        return None

    target_naive = _target_naive(target)
    best_idx: Optional[int] = None
    best_diff = float("inf")
    for index, timestamp in enumerate(timestamps):
        if timestamp is None or index >= len(values):
            continue
        diff = abs((timestamp - target_naive).total_seconds())
        if diff < best_diff:
            best_diff = diff
            best_idx = index

    return values[best_idx] if best_idx is not None else None


def _round_optional(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(value, digits) if value is not None else None


def _build_10min_timeline(
    hourly: Dict[str, Any],
    activity: Activity,
) -> List[Dict[str, Any]]:
    """Construit une timeline meteo toutes les 10 minutes depuis le depart."""
    hours = hourly.get("time", [])
    if not isinstance(hours, list) or not hours:
        return []

    duration_seconds = _activity_duration_seconds(activity)
    duration_min = max(0, int(round(duration_seconds / 60)))
    timestamps = _hour_datetimes(hours)
    start = activity.start_date

    sample_minutes = list(range(0, duration_min + 1, WEATHER_TIMELINE_INTERVAL_MIN))
    if duration_min not in sample_minutes:
        sample_minutes.append(duration_min)
    if not sample_minutes:
        sample_minutes = [0]

    timeline: List[Dict[str, Any]] = []
    for elapsed_min in sample_minutes:
        target = start + timedelta(minutes=elapsed_min)
        weather_code = _nearest_hour_value(timestamps, hourly.get("weather_code"), target)
        try:
            weather_code_value = int(weather_code) if weather_code is not None else None
        except (TypeError, ValueError):
            weather_code_value = None

        timeline.append({
            "elapsed_min": elapsed_min,
            "timestamp": _target_naive(target).isoformat(),
            "temperature_c": _round_optional(
                _interpolate_hourly_value(timestamps, hourly.get("temperature_2m"), target),
                1,
            ),
            "apparent_temperature_c": _round_optional(
                _interpolate_hourly_value(timestamps, hourly.get("apparent_temperature"), target),
                1,
            ),
            "humidity_pct": _round_optional(
                _interpolate_hourly_value(timestamps, hourly.get("relative_humidity_2m"), target),
                0,
            ),
            "wind_speed_kmh": _round_optional(
                _interpolate_hourly_value(timestamps, hourly.get("wind_speed_10m"), target),
                1,
            ),
            "precipitation_mm": _round_optional(
                _interpolate_hourly_value(timestamps, hourly.get("precipitation"), target),
                2,
            ),
            "weather_code": weather_code_value,
        })

    return timeline


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

    def _parse_sampled_at(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    sampled_time = hours[idx] if idx < len(hours) else None
    hourly_snapshot: Dict[str, Any] = {"time": sampled_time}
    for key, values in hourly.items():
        if key == "time" or not isinstance(values, list):
            continue
        hourly_snapshot[key] = values[idx] if idx < len(values) else None
    timeline_10min = _build_10min_timeline(hourly, activity)
    hourly_snapshot["timeline_interval_min"] = WEATHER_TIMELINE_INTERVAL_MIN
    hourly_snapshot["timeline_duration_min"] = max(0, round(_activity_duration_seconds(activity) / 60, 1))
    hourly_snapshot["timeline_10min"] = timeline_10min

    request_meta = data.get("_athletiq_request", {})

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
        sampled_at=_parse_sampled_at(sampled_time),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        elevation_m=data.get("elevation"),
        source_endpoint=request_meta.get("template"),
        source_url=request_meta.get("base_url"),
        request_params=request_meta.get("params"),
        hourly_units=data.get("hourly_units"),
        hourly_snapshot=hourly_snapshot,
    )


WEATHER_REFRESH_FIELDS = (
    "temperature_c",
    "humidity_pct",
    "wind_speed_kmh",
    "wind_direction_deg",
    "pressure_hpa",
    "precipitation_mm",
    "cloud_cover_pct",
    "weather_code",
    "sampled_at",
    "latitude",
    "longitude",
    "elevation_m",
    "source_endpoint",
    "source_url",
    "request_params",
    "hourly_units",
    "hourly_snapshot",
)


def _apply_weather_update(target: ActivityWeather, source: ActivityWeather) -> ActivityWeather:
    """Copie les champs meteo recalcules sur une ligne existante."""
    for field_name in WEATHER_REFRESH_FIELDS:
        setattr(target, field_name, getattr(source, field_name))
    return target


def _weather_needs_template_refresh(weather: ActivityWeather) -> bool:
    """Detecte les anciennes lignes meteo sans payload extensible."""
    if not weather.hourly_snapshot or not weather.request_params:
        return True
    if not isinstance(weather.hourly_snapshot, dict):
        return False
    timeline = weather.hourly_snapshot.get("timeline_10min")
    return not isinstance(timeline, list) or len(timeline) == 0


def _get_weather_record(session: Session, activity_id: UUID) -> Optional[ActivityWeather]:
    return session.exec(
        select(ActivityWeather).where(ActivityWeather.activity_id == activity_id).limit(1)
    ).first()


async def _call_open_meteo(
    lat: float,
    lon: float,
    date: datetime,
    client: httpx.AsyncClient,
    duration_seconds: int = 0,
) -> Optional[Dict[str, Any]]:
    """Appelle Open-Meteo (Historical ou Forecast selon l'age de l'activite)."""
    date_str = date.strftime("%Y-%m-%d")
    base_url, params, template_name = _build_open_meteo_request(lat, lon, date, duration_seconds)
    timeout_s = (
        HISTORICAL_REQUEST_TIMEOUT_S
        if template_name == "historical_archive"
        else REQUEST_TIMEOUT_S
    )

    for attempt in range(OPEN_METEO_MAX_ATTEMPTS):
        try:
            resp = await client.get(base_url, params=params, timeout=timeout_s)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict):
                return {
                    **payload,
                    "_athletiq_request": {
                        "template": template_name,
                        "base_url": base_url,
                        "params": params,
                    },
                }
            return payload
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < OPEN_METEO_MAX_ATTEMPTS - 1:
                await asyncio.sleep(OPEN_METEO_RATE_LIMIT_BACKOFF_S)
                continue
            logger.warning(f"Open-Meteo HTTP {e.response.status_code} pour ({lat},{lon}) {date_str}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"Open-Meteo erreur reseau pour ({lat},{lon}) {date_str}: {e}")
            return None

    return None


async def fetch_weather_for_activity(
    session: Session,
    activity: Activity,
    client: Optional[httpx.AsyncClient] = None,
) -> bool:
    """Recupere la meteo pour une activite et la stocke en base.

    Retourne True si la meteo a ete fetched et stockee, False sinon.
    """
    existing_weather = _get_weather_record(session, activity.id)
    if existing_weather is not None and not _weather_needs_template_refresh(existing_weather):
        return True

    gps = _extract_activity_gps(activity)
    if gps is None:
        logger.info(f"Activite {activity.id}: pas de coordonnees GPS exploitables, skip meteo")
        return False

    lat, lon = gps

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient()

    try:
        data = await _call_open_meteo(
            lat,
            lon,
            activity.start_date,
            client,
            _activity_duration_seconds(activity),
        )
        if data is None:
            return False

        weather = _build_weather_from_response(data, activity)
        if weather is None:
            logger.warning(f"Activite {activity.id}: reponse Open-Meteo vide ou invalide")
            return False

        if existing_weather is not None:
            weather = _apply_weather_update(existing_weather, weather)

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
    max_activities: int = DEFAULT_BATCH_SIZE,
    concurrency: int = DEFAULT_CONCURRENCY,
    include_historical_archive: bool = False,
    days_back: Optional[int] = None,
) -> Dict[str, Any]:
    """Enrichit un lot d'activites avec coordonnees GPS pas encore enrichies en meteo.

    Retourne un resume {processed, skipped, errors, remaining}. Le traitement est
    volontairement borne pour eviter de bloquer le backend si Open-Meteo ne repond pas.
    """
    query = select(Activity).where(Activity.source == ActivitySource.GARMIN.value)
    if user_id:
        query = query.where(Activity.user_id == user_id)
    if days_back is not None:
        query = query.where(Activity.start_date >= datetime.utcnow() - timedelta(days=days_back))

    activities = session.exec(query.order_by(Activity.start_date.desc())).all()

    processed = 0
    skipped = 0
    errors = 0
    archive_required = 0

    candidates: list[tuple[Activity, tuple[float, float], Optional[ActivityWeather]]] = []
    for activity in activities:
        existing_weather = _get_weather_record(session, activity.id)
        if existing_weather is not None and not _weather_needs_template_refresh(existing_weather):
            skipped += 1
            continue

        gps = _extract_activity_gps(activity)
        if gps is None:
            skipped += 1
            continue

        forecast_supported = _is_forecast_api_supported(activity.start_date)

        if include_historical_archive and forecast_supported:
            skipped += 1
            continue

        if not include_historical_archive and not forecast_supported:
            archive_required += 1
            continue

        candidates.append((activity, gps, existing_weather))

    batch_size = max(1, max_activities)
    batch = candidates[:batch_size]
    remaining = max(0, len(candidates) - len(batch))

    if not batch:
        return {
            "processed": processed,
            "skipped": skipped,
            "errors": errors,
            "remaining": remaining,
            "archive_required": archive_required,
        }

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def _fetch(activity: Activity, gps: tuple[float, float]) -> Optional[ActivityWeather]:
        async with semaphore:
            lat, lon = gps
            data = await _call_open_meteo(
                lat,
                lon,
                activity.start_date,
                client,
                _activity_duration_seconds(activity),
            )
            await asyncio.sleep(REQUEST_DELAY_S)
            if data is None:
                return None
            return _build_weather_from_response(data, activity)

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *(_fetch(activity, gps) for activity, gps, _existing_weather in batch),
            return_exceptions=True,
        )

        for activity_result, (_activity, _gps, _existing_weather) in zip(results, batch):
            if isinstance(activity_result, Exception):
                logger.error(f"Erreur meteo batch: {activity_result}")
                errors += 1
                continue

            if activity_result is None:
                errors += 1
                continue

            latest_weather = _get_weather_record(session, activity_result.activity_id)
            if latest_weather is not None:
                activity_result = _apply_weather_update(latest_weather, activity_result)

            try:
                session.add(activity_result)
                session.commit()
                processed += 1
            except IntegrityError:
                session.rollback()
                concurrent_weather = _get_weather_record(session, activity_result.activity_id)
                if concurrent_weather is None:
                    logger.error(
                        "Conflit meteo activity_id=%s sans ligne recuperable",
                        activity_result.activity_id,
                    )
                    errors += 1
                    continue

                try:
                    session.add(_apply_weather_update(concurrent_weather, activity_result))
                    session.commit()
                    processed += 1
                except Exception as exc:
                    session.rollback()
                    logger.error(
                        "Erreur mise a jour meteo concurrente activity_id=%s: %s",
                        activity_result.activity_id,
                        exc,
                    )
                    errors += 1
            except Exception as exc:
                session.rollback()
                logger.error(
                    "Erreur persistance meteo activity_id=%s: %s",
                    activity_result.activity_id,
                    exc,
                )
                errors += 1

    return {
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
        "remaining": remaining,
        "archive_required": archive_required,
    }


def get_weather_enrichment_status(session: Session, user_id: UUID) -> Dict[str, int]:
    """Retourne le statut meteo en tenant compte des coordonnees disponibles."""
    activities = session.exec(
        select(Activity).where(
            Activity.user_id == user_id,
            Activity.source == ActivitySource.GARMIN.value,
        )
    ).all()

    eligible_activities = [
        activity
        for activity in activities
        if activity.id is not None and _extract_activity_gps(activity) is not None
    ]
    eligible_activity_ids = [activity.id for activity in eligible_activities]
    eligible = len(eligible_activity_ids)
    with_streams = sum(1 for activity in activities if _parse_streams(activity) is not None)
    forecast_supported = sum(
        1
        for activity in eligible_activities
        if _is_forecast_api_supported(activity.start_date)
    )

    weather_activity_ids = set()
    weather_payload_activity_ids = set()
    weather_timeline_activity_ids = set()
    if eligible_activity_ids:
        fetched_weather_rows = session.exec(
            select(ActivityWeather.activity_id, ActivityWeather.hourly_snapshot).where(
                ActivityWeather.activity_id.in_(eligible_activity_ids)
            )
        ).all()
        weather_activity_ids = {row[0] for row in fetched_weather_rows}
        weather_payload_activity_ids = {row[0] for row in fetched_weather_rows if row[1]}
        weather_timeline_activity_ids = {
            row[0]
            for row in fetched_weather_rows
            if isinstance(row[1], dict) and isinstance(row[1].get("timeline_10min"), list)
        }

    with_weather = len(weather_activity_ids)
    with_weather_payload = len(weather_payload_activity_ids)
    with_weather_timeline = len(weather_timeline_activity_ids)
    archive_required = sum(
        1
        for activity in eligible_activities
        if (
            activity.id not in weather_activity_ids
            or activity.id not in weather_timeline_activity_ids
        )
        and not _is_forecast_api_supported(activity.start_date)
    )

    return {
        "total_activities": len(activities),
        "with_streams": with_streams,
        "with_coordinates": eligible,
        "eligible_weather_activities": eligible,
        "with_weather": with_weather,
        "with_weather_payload": with_weather_payload,
        "with_weather_timeline": with_weather_timeline,
        "pending_weather": max(0, eligible - with_weather),
        "pending_weather_payload": max(0, with_weather - with_weather_payload),
        "pending_weather_timeline": max(0, with_weather - with_weather_timeline),
        "without_coordinates": max(0, len(activities) - eligible),
        "forecast_supported_activities": forecast_supported,
        "archive_required_activities": archive_required,
    }


def is_weather_fetched(session: Session, activity_id: UUID) -> bool:
    """Verifie si la meteo a deja ete recuperee pour cette activite."""
    return _get_weather_record(session, activity_id) is not None
