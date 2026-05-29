"""Production-parity FC-band audit for Race Predictor V2.3.1.

This script intentionally imports the observation aggregator's internal
selection and extraction helpers. An audit that uses a wider activity pool
than production gives a false impression of calibration coverage.

Current production policy is explicit: only Garmin-enriched activities are
queried by ``_fetch_user_activities``. The policy avoids implicit duplicate
fusion while a canonical Strava/Garmin deduplication layer is not available.
"""
from __future__ import annotations

import os
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

os.environ.setdefault("DATABASE_URL", "sqlite:///./stridedelta.db")
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import Session  # noqa: E402

from app.core.database import engine as db_engine  # noqa: E402
from app.domain.services.race_predictor.observation_aggregator import (  # noqa: E402
    DEFAULT_HISTORY_WINDOW_DAYS,
    FC_BAND_FALLBACK,
    FC_BAND_PRIMARY,
    MIN_ACTIVITIES_IN_BAND,
    MIN_SAMPLES_IN_BAND,
    _build_p_ref_steady_observations,
    _estimate_fcmax_from_history,
    _fetch_user_activities,
    _fetch_validation_index,
    _try_band,
    categorize_activity,
)

USER_ID = UUID("b5727f6086db41ab86e2bc803460b868")
FULL_SNAPSHOT_CUTOFF = datetime(2026, 5, 26, 23, 59, 59)
PRE_UTMJ_CUTOFF = datetime(2025, 10, 4, 6, 30)
CANDIDATE_BANDS = [
    (0.65, 0.85),  # historical comparison only
    FC_BAND_PRIMARY,
    FC_BAND_FALLBACK,
]


@dataclass
class BandRow:
    mode: str
    band: tuple[float, float]
    selected: bool
    selected_status: str
    fcmax_bpm: float
    fcmax_source: str
    queried_activities: int
    eligible_activities: int
    observation_count: int
    samples_in_band: int
    activities_in_band: int
    median_observation_wkg: float | None


def _categorised_production_pool(
    session: Session, as_of_date: datetime
) -> tuple[list[tuple[Any, str]], int]:
    activities = _fetch_user_activities(
        session,
        USER_ID,
        as_of_date=as_of_date,
        excluded_ids=set(),
        history_start_date=as_of_date - timedelta(days=DEFAULT_HISTORY_WINDOW_DAYS),
    )
    validations = _fetch_validation_index(
        session,
        USER_ID,
        activity_ids={activity.id for activity in activities if activity.id is not None},
    )
    categorised: list[tuple[Any, str]] = []
    for activity in activities:
        category = categorize_activity(activity, validations.get(activity.id))
        if category != "non_scoring":
            categorised.append((activity, category))
    return categorised, len(activities)


def run_mode(session: Session, label: str, as_of_date: datetime) -> list[BandRow]:
    categorised, queried_count = _categorised_production_pool(session, as_of_date)
    fc_debug: dict[str, Any] = {}
    fcmax = float(_estimate_fcmax_from_history(categorised, debug_trace=fc_debug) or 190.0)
    _, selected_meta = _build_p_ref_steady_observations(
        categorised, fcmax_estimate=fcmax
    )
    selected_band = tuple(selected_meta["fc_band_used"])
    production_has_evidence = (
        int(selected_meta["samples_in_band"]) >= MIN_SAMPLES_IN_BAND
        and int(selected_meta["activities_in_band"]) >= MIN_ACTIVITIES_IN_BAND
    )

    rows: list[BandRow] = []
    for band in CANDIDATE_BANDS:
        observations, samples, contributing = _try_band(
            categorised,
            fcmax_estimate=fcmax,
            band=band,
            std_multiplier=1.0,
            fallback_used=False,
        )
        means = [float(obs["mean"]) for obs in observations]
        rows.append(
            BandRow(
                mode=label,
                band=band,
                selected=tuple(band) == selected_band,
                selected_status=(
                    "evidence"
                    if tuple(band) == selected_band and production_has_evidence
                    else "prior_only"
                    if tuple(band) == selected_band
                    else "-"
                ),
                fcmax_bpm=fcmax,
                fcmax_source=str(fc_debug.get("fcmax_source", "none")),
                queried_activities=queried_count,
                eligible_activities=len(categorised),
                observation_count=len(observations),
                samples_in_band=samples,
                activities_in_band=contributing,
                median_observation_wkg=statistics.median(means) if means else None,
            )
        )
    return rows


def format_report(rows: list[BandRow]) -> str:
    lines = [
        "# Audit FC band V2.3.1 - parite production",
        "",
        f"User ID: `{USER_ID.hex}`",
        "",
        "Politique source production: `Activity.source == \"garmin\"` uniquement.",
        "L'audit n'ajoute pas les activites Strava ou manual et applique les validations/categorisations de l'agregateur.",
        (
            "Une bande selectionnee sans au moins "
            f"{MIN_ACTIVITIES_IN_BAND} observations et {MIN_SAMPLES_IN_BAND} samples "
            "aboutit a un posterior domine par le prior."
        ),
        "",
        "| Fenetre | Bande | Choisie/statut | FCmax/source | Activites requetees/eligibles | Observations P_ref | Samples/contributeurs | Mediane P_ref (W/kg) |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        median = (
            f"{row.median_observation_wkg:.2f}"
            if row.median_observation_wkg is not None
            else "n/a"
        )
        lines.append(
            f"| {row.mode} | [{row.band[0]:.2f}, {row.band[1]:.2f}] | "
            f"{'oui / ' + row.selected_status if row.selected else 'non'} | {row.fcmax_bpm:.1f} / {row.fcmax_source} | "
            f"{row.queried_activities} / {row.eligible_activities} | "
            f"{row.observation_count} | {row.samples_in_band} / {row.activities_in_band} | {median} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    rows: list[BandRow] = []
    with Session(db_engine) as session:
        rows.extend(run_mode(session, "snapshot_2026-05-26", FULL_SNAPSHOT_CUTOFF))
        rows.extend(run_mode(session, "pre_UTMJ", PRE_UTMJ_CUTOFF))
    report = format_report(rows)
    out_path = Path("/tmp/audit_fc_band_results.md")
    out_path.write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    sys.stdout.write(f"\nWrote {out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
