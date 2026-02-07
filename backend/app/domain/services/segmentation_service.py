"""
Service de segmentation des streams Strava en segments de ~100m.
Tache 1.2.1 : segment_activity(), segment_all_enriched(), is_activity_segmented()
Inclut 1.2.2 (decoupage 100m), 1.2.3 (bug "null"), 1.2.4 (pace_min_per_km).
"""
import json
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlmodel import Session, select

from app.domain.entities.activity import Activity
from app.domain.entities.segment import Segment
from app.domain.entities.segment_features import SegmentFeatures

logger = logging.getLogger(__name__)

SEGMENT_LENGTH_M = 100


def _parse_streams(activity: Activity) -> Optional[Dict[str, Any]]:
    """Extrait streams_data en gerant le bug connu 'null' string (tache 1.2.3)."""
    raw = activity.streams_data
    if raw is None:
        return None
    # Bug connu : streams_data stocke comme la string "null"
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


def _get_data(streams: Dict[str, Any], key: str) -> Optional[List]:
    """Recupere streams[key]['data'] si present."""
    entry = streams.get(key)
    if entry is None:
        return None
    if isinstance(entry, dict):
        return entry.get("data")
    if isinstance(entry, list):
        return entry
    return None


def _mean(values: List[float]) -> Optional[float]:
    """Moyenne d'une liste, None si vide."""
    if not values:
        return None
    return sum(values) / len(values)


def segment_activity(
    session: Session,
    activity: Activity,
) -> int:
    """Segmente une activite en tranches de ~100m.

    Retourne le nombre de segments crees.
    Supprime les anciens segments de cette activite avant re-segmentation.
    """
    streams = _parse_streams(activity)
    if streams is None:
        logger.warning(f"Activite {activity.id}: streams_data absent ou null, skip")
        return 0

    distance_data = _get_data(streams, "distance")
    time_data = _get_data(streams, "time")
    if not distance_data or not time_data or len(distance_data) < 2:
        logger.warning(f"Activite {activity.id}: distance/time data insuffisant, skip")
        return 0

    n = len(distance_data)

    # Streams optionnels
    hr_data = _get_data(streams, "heartrate")
    cadence_data = _get_data(streams, "cadence")
    grade_data = _get_data(streams, "grade_smooth")
    altitude_data = _get_data(streams, "altitude")
    latlng_data = _get_data(streams, "latlng")

    total_distance = distance_data[-1] if distance_data else 0

    # Supprimer anciens segments (re-segmentation)
    old_segments = session.exec(
        select(Segment).where(Segment.activity_id == activity.id)
    ).all()
    for seg in old_segments:
        # Supprimer les features liees
        old_features = session.exec(
            select(SegmentFeatures).where(SegmentFeatures.segment_id == seg.id)
        ).all()
        for feat in old_features:
            session.delete(feat)
        session.delete(seg)
    if old_segments:
        session.flush()

    # Decoupage en segments de ~100m
    segments_created = []
    seg_start_idx = 0
    seg_start_dist = 0.0
    segment_index = 0

    cumulative_elev_gain = 0.0
    cumulative_elev_loss = 0.0
    cumulative_time_s = 0.0

    for i in range(1, n):
        current_dist = distance_data[i]
        seg_dist = current_dist - seg_start_dist

        if seg_dist >= SEGMENT_LENGTH_M or i == n - 1:
            # Indices du segment : seg_start_idx..i (inclus)
            seg_end_idx = i

            # Distance et temps du segment
            dist_m = distance_data[seg_end_idx] - distance_data[seg_start_idx]
            elapsed_s = time_data[seg_end_idx] - time_data[seg_start_idx]

            if dist_m <= 0:
                seg_start_idx = seg_end_idx
                seg_start_dist = distance_data[seg_end_idx]
                continue

            # Pace (tache 1.2.4)
            pace = (elapsed_s / 60.0) / (dist_m / 1000.0) if dist_m > 0 else None

            # Moyennes HR, cadence, grade
            slice_range = range(seg_start_idx, seg_end_idx + 1)

            avg_hr = None
            if hr_data and len(hr_data) > seg_end_idx:
                hr_vals = [hr_data[j] for j in slice_range if hr_data[j] is not None]
                avg_hr = _mean(hr_vals)

            avg_cadence = None
            if cadence_data and len(cadence_data) > seg_end_idx:
                cad_vals = [cadence_data[j] for j in slice_range if cadence_data[j] is not None]
                avg_cadence = _mean(cad_vals)

            avg_grade = None
            if grade_data and len(grade_data) > seg_end_idx:
                grade_vals = [grade_data[j] for j in slice_range if grade_data[j] is not None]
                avg_grade = _mean(grade_vals)

            # Elevation gain/loss et altitude moyenne
            elev_gain = 0.0
            elev_loss = 0.0
            alt_mean = None
            if altitude_data and len(altitude_data) > seg_end_idx:
                alt_vals = [altitude_data[j] for j in slice_range if altitude_data[j] is not None]
                alt_mean = _mean(alt_vals)
                for j in range(seg_start_idx + 1, seg_end_idx + 1):
                    if altitude_data[j] is not None and altitude_data[j - 1] is not None:
                        diff = altitude_data[j] - altitude_data[j - 1]
                        if diff > 0:
                            elev_gain += diff
                        else:
                            elev_loss += abs(diff)

            # Midpoint GPS
            lat, lon = None, None
            if latlng_data and len(latlng_data) > seg_end_idx:
                mid_idx = (seg_start_idx + seg_end_idx) // 2
                point = latlng_data[mid_idx]
                if isinstance(point, (list, tuple)) and len(point) == 2:
                    lat, lon = point[0], point[1]

            segment = Segment(
                activity_id=activity.id,
                user_id=activity.user_id,
                segment_index=segment_index,
                distance_m=dist_m,
                elapsed_time_s=elapsed_s,
                avg_grade_percent=avg_grade,
                elevation_gain_m=elev_gain,
                elevation_loss_m=elev_loss,
                altitude_m=alt_mean,
                avg_hr=avg_hr,
                avg_cadence=avg_cadence,
                lat=lat,
                lon=lon,
                pace_min_per_km=pace,
            )
            session.add(segment)
            session.flush()  # pour obtenir segment.id

            # Cumulatifs pour SegmentFeatures
            cumulative_elev_gain += elev_gain
            cumulative_elev_loss += elev_loss
            cumulative_time_s += elapsed_s
            cumul_dist_km = distance_data[seg_end_idx] / 1000.0

            race_pct = (distance_data[seg_end_idx] / total_distance * 100.0) if total_distance > 0 else None

            intensity = None
            if avg_hr is not None:
                intensity = avg_hr * (dist_m / 1000.0)

            features = SegmentFeatures(
                segment_id=segment.id,
                activity_id=activity.id,
                cumulative_distance_km=cumul_dist_km,
                elapsed_time_min=cumulative_time_s / 60.0,
                cumulative_elev_gain_m=cumulative_elev_gain,
                cumulative_elev_loss_m=cumulative_elev_loss,
                race_completion_pct=race_pct,
                intensity_proxy=intensity,
            )
            session.add(features)

            segments_created.append(segment)
            segment_index += 1
            seg_start_idx = seg_end_idx
            seg_start_dist = distance_data[seg_end_idx]

    session.commit()
    logger.info(f"Activite {activity.id}: {len(segments_created)} segments crees")
    return len(segments_created)


def segment_all_enriched(session: Session, user_id: Optional[UUID] = None) -> Dict[str, Any]:
    """Segmente toutes les activites enrichies (streams_data non null) pas encore segmentees.

    Si user_id est fourni, limite a cet utilisateur.
    Retourne un resume {processed, skipped, errors}.
    """
    query = select(Activity).where(Activity.streams_data.is_not(None))
    if user_id:
        query = query.where(Activity.user_id == user_id)

    activities = session.exec(query).all()

    processed = 0
    skipped = 0
    errors = 0

    for activity in activities:
        if is_activity_segmented(session, activity.id):
            skipped += 1
            continue
        try:
            count = segment_activity(session, activity)
            if count > 0:
                processed += 1
            else:
                skipped += 1
        except Exception as e:
            logger.error(f"Erreur segmentation activite {activity.id}: {e}")
            session.rollback()
            errors += 1

    return {"processed": processed, "skipped": skipped, "errors": errors}


def is_activity_segmented(session: Session, activity_id: UUID) -> bool:
    """Verifie si une activite a deja ete segmentee."""
    segment = session.exec(
        select(Segment).where(Segment.activity_id == activity_id).limit(1)
    ).first()
    return segment is not None
