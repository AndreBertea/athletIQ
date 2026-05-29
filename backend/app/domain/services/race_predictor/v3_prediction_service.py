"""Race Predictor V3: physical prediction with automatic residual learning.

V3 runs the V2.3.1 physics and uncertainty pipeline with sparse Garmin
evidence, then applies an athlete-specific residual correction trained from
the top 25% scored reference activities over the last year. The residual layer
is recalculated automatically, so the user does not need to manually validate
sessions before V3 becomes useful.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlmodel import Session

from app.domain.services.race_predictor.observation_aggregator import (
    SPARSE_EVIDENCE_POLICY,
)
from app.domain.services.race_predictor.v2_3_prediction_service import predict_v2_3
from app.domain.services.race_predictor.v3_residual_service import (
    apply_v3_residual_correction,
    get_or_train_v3_residual_model,
)

ENGINE_VERSION = "v3_hybrid"
BASE_ENGINE_VERSION = "v2_3_1_bayesian"

def predict_v3(
    session: Session,
    user_id: UUID,
    gpx_text: str,
    *,
    race_datetime: Optional[datetime],
    effort_mode: str,
    analysis_mode: str,
    target_heartrate: Optional[float],
    weather_mode: str,
    manual_temperature_c: Optional[float],
    ravito_mode: str,
    custom_ravitos: Optional[list[dict[str, Any]]] = None,
    as_of_date: Optional[datetime] = None,
    excluded_activity_ids: Optional[Iterable[UUID]] = None,
    history_start_date: Optional[datetime] = None,
    filename: Optional[str] = None,
) -> dict[str, Any]:
    """Return a V3 prediction with automatic top-score residual correction."""
    result = predict_v2_3(
        session,
        user_id,
        gpx_text,
        race_datetime=race_datetime,
        effort_mode=effort_mode,
        analysis_mode=analysis_mode,
        target_heartrate=target_heartrate,
        weather_mode=weather_mode,
        manual_temperature_c=manual_temperature_c,
        ravito_mode=ravito_mode,
        custom_ravitos=custom_ravitos,
        as_of_date=as_of_date,
        excluded_activity_ids=excluded_activity_ids,
        history_start_date=history_start_date,
        filename=filename,
        evidence_policy=SPARSE_EVIDENCE_POLICY,
    )

    result["engine_version"] = ENGINE_VERSION
    calibration = result.setdefault("calibration", {})
    calibration["engine_version"] = ENGINE_VERSION
    calibration["source"] = "v3_weighted_sparse_garmin_posterior"
    result["hybrid_model"] = {
        "physics_base": BASE_ENGINE_VERSION,
        "evidence_policy": SPARSE_EVIDENCE_POLICY,
        "trail_factor": (
            result.get("athlete_model", {})
            .get("debug_trace", {})
            .get("trail_factor", {})
        ),
    }

    debug_trace = result.setdefault("debug_trace", {})
    debug_trace["engine_version"] = ENGINE_VERSION
    debug_trace["base_engine_version"] = BASE_ENGINE_VERSION
    debug_trace["hybrid_model"] = result["hybrid_model"]
    debug_trace["v3_sparse_evidence"] = (
        debug_trace.get("aggregator", {}).get("sparse_evidence_accepted", False)
    )

    residual_model = get_or_train_v3_residual_model(
        session,
        user_id,
        as_of_date=as_of_date or datetime.utcnow(),
        history_start_date=history_start_date,
    )
    apply_v3_residual_correction(result, residual_model)
    return result


__all__ = ["predict_v3", "ENGINE_VERSION", "BASE_ENGINE_VERSION"]
