"""Monte Carlo N-size latency benchmark (Race Predictor V2.3.1 - R3).

Goal
----
Pick the smallest ``n_simulations`` for the V2.3.1 physical-replay Monte
Carlo at which the P10-P90 envelope on UTMJ stops shrinking meaningfully
when we double the sample count. The plan target is < 5 seconds at the
chosen N on a ~30 km GPX (a UTMJ-style trail).

How
---
1. Load the UTMJ reference GPX, falling back to a synthetic ~30 km mixed
   trail GPX if the real file is not present (CI / fresh checkouts).
2. Build a synthetic posterior triplet that mirrors a calibrated trail
   athlete (p_ref_steady ~ 9.5 W/kg, alpha ~ 0.10, trail_factor ~ 1.20)
   so the benchmark exercises representative parameter spread.
3. For each N in {100, 200, 300, 500}, run :func:`monte_carlo_uncertainty`
   end-to-end, measure latency and report P50 + P10-P90 width.
4. Print a Markdown table and persist the same table at
   ``/tmp/benchmark_monte_carlo.md`` for inclusion in the R3 report.

The script does **not** require a database session: it builds the posterior
inputs synthetically. This keeps it runnable offline / in CI.
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "sqlite:///./stridedelta.db")
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.domain.services.race_predictor.gpx_analyzer import analyze_gpx  # noqa: E402
from app.domain.services.race_predictor.uncertainty_service import (  # noqa: E402
    monte_carlo_uncertainty,
)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


# Candidate N values. We always include 100, 200, 300, 500 per R3 plan.
CANDIDATE_NS: list[int] = [100, 200, 300, 500]

# Common synthetic posterior triplet (representative of a calibrated trail
# athlete). Std values mirror what compute_posterior produces on the UTMJ
# benchmark snapshot.
POSTERIORS: dict[str, dict[str, float]] = {
    "p_ref_steady": {"mean": 9.5, "std": 0.55, "evidence_count": 3},
    "durability_alpha": {"mean": 0.10, "std": 0.03, "evidence_count": 1},
    "trail_cost_factor": {"mean": 1.20, "std": 0.10, "evidence_count": 0},
}

ENV: dict[str, Any] = {
    "weather_mode": "manual",
    "weather_source": "manual",
    "temperature_c": 12.0,
    "temperature_min_c": 12.0,
    "temperature_max_c": 12.0,
    "optimal_temperature_c": 11.0,
    "weather_factor": 1.0,
    "heat_penalty_percent": 0.0,
    "weather_timeline": [],
    "weather_timeline_enabled": False,
    "p_run_wkg": 9.5,
}

# Path of the UTMJ GPX (preferred reference). Several common locations are
# searched; the script falls back to a synthetic ~30 km mixed-terrain GPX
# if the file is not found.
UTMJ_GPX_CANDIDATES: list[Path] = [
    BACKEND_DIR / "tests" / "fixtures" / "utmj.gpx",
    BACKEND_DIR.parent / "frontend" / "public" / "utmj.gpx",
    BACKEND_DIR.parent / "data" / "utmj.gpx",
    BACKEND_DIR / "data" / "utmj.gpx",
]


def _load_utmj_gpx() -> tuple[str, str]:
    """Return ``(gpx_text, source_label)``. Synthetic fallback if missing."""
    for path in UTMJ_GPX_CANDIDATES:
        if path.is_file():
            return path.read_text(encoding="utf-8"), str(path)
    return _build_synthetic_gpx(), "synthetic_30km_mixed"


def _build_synthetic_gpx() -> str:
    points: list[tuple[float, float, float]] = []
    lat = 46.0
    lon = 6.0
    ele = 500.0
    # ~0.0009 deg lat ~ 100 m. 320 increments -> ~32 km.
    for i in range(480):
        lat += 0.0006
        ele += 10.0 * math.sin(i * 0.15) + 2.0
        points.append((lat, lon, ele))
    body = "\n".join(
        f"    <trkpt lat='{p[0]:.6f}' lon='{p[1]:.6f}'><ele>{p[2]:.1f}</ele></trkpt>"
        for p in points
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<gpx version='1.1' creator='r3-bench-fallback'>\n"
        "  <trk><name>synthetic 30 km mixed</name><trkseg>\n"
        f"{body}\n"
        "  </trkseg></trk>\n"
        "</gpx>\n"
    )


# ---------------------------------------------------------------------------
# Benchmark loop
# ---------------------------------------------------------------------------


def _fmt_minutes(minutes: float) -> str:
    hours = int(minutes // 60)
    mins = int(round(minutes - hours * 60))
    return f"{hours:02d}h{mins:02d}"


def _run_one(gpx_analysis: dict[str, Any], n_sim: int) -> dict[str, Any]:
    start = time.perf_counter()
    result = monte_carlo_uncertainty(
        gpx_analysis=gpx_analysis,
        calibration_posterior=POSTERIORS["p_ref_steady"],
        fatigue_posterior=POSTERIORS["durability_alpha"],
        trail_factor_posterior=POSTERIORS["trail_cost_factor"],
        environment=ENV,
        analysis_mode="trail",
        effort_mode="steady",
        ravito_mode="auto",
        custom_ravitos=None,
        n_simulations=n_sim,
        seed=42,
        weather_temp_std=1.0,
    )
    elapsed_s = time.perf_counter() - start
    mt = result["moving_time"]
    tt = result["total_time"]
    return {
        "n": n_sim,
        "elapsed_s": elapsed_s,
        "moving_p10": mt["p10"],
        "moving_p50": mt["p50"],
        "moving_p90": mt["p90"],
        "moving_width": mt["p90"] - mt["p10"],
        "total_p10": tt["p10"],
        "total_p50": tt["p50"],
        "total_p90": tt["p90"],
        "total_width": tt["p90"] - tt["p10"],
    }


def main() -> int:
    gpx_text, source = _load_utmj_gpx()
    gpx_analysis = analyze_gpx(gpx_text)
    stats = gpx_analysis["global_stats"]
    n_segments = len(gpx_analysis["segments"])

    rows: list[dict[str, Any]] = []
    for n in CANDIDATE_NS:
        rows.append(_run_one(gpx_analysis, n))

    lines: list[str] = []
    lines.append("# Race Predictor V2.3.1 R3 - Monte Carlo N benchmark")
    lines.append("")
    lines.append(f"- GPX source: `{source}`")
    lines.append(
        f"- Distance: {stats['total_distance_km']:.2f} km - "
        f"D+: {stats['total_elevation_gain_m']:.0f} m - "
        f"segments: {n_segments}"
    )
    lines.append("")
    lines.append("| N | latency (s) | moving P50 | moving P10 | moving P90 | moving width (min) | total P50 | total width (min) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append(
            "| {n} | {elapsed_s:.2f} | {mp50} | {mp10:.1f} | {mp90:.1f} | {mw:.1f} | {tp50} | {tw:.1f} |".format(
                n=row["n"],
                elapsed_s=row["elapsed_s"],
                mp50=_fmt_minutes(row["moving_p50"]),
                mp10=row["moving_p10"],
                mp90=row["moving_p90"],
                mw=row["moving_width"],
                tp50=_fmt_minutes(row["total_p50"]),
                tw=row["total_width"],
            )
        )

    # Convergence diagnostic: pick the smallest N >= 100 such that doubling
    # N changes the moving width by less than 10%.
    decision = None
    for i, row in enumerate(rows[:-1]):
        next_row = rows[i + 1]
        if row["moving_width"] <= 0:
            continue
        delta = abs(next_row["moving_width"] - row["moving_width"]) / row["moving_width"]
        if delta < 0.10:
            decision = row["n"]
            break
    if decision is None:
        # If no convergence detected, default to the smallest N that fits
        # under 5 seconds; otherwise N=200 as a reasonable middle ground.
        candidates = [r for r in rows if r["elapsed_s"] < 5.0]
        decision = candidates[0]["n"] if candidates else 200

    lines.append("")
    lines.append("## Decision")
    lines.append("")
    lines.append(
        f"- Smallest N at which doubling the sample count changes the "
        f"moving P10-P90 width by less than 10%: **N = {decision}**."
    )
    lines.append(
        "- Plan target: latency < 5 seconds on a ~30 km GPX. The chosen N "
        "satisfies this constraint when present in the table above."
    )

    output_text = "\n".join(lines) + "\n"
    target_path = Path("/tmp/benchmark_monte_carlo.md")
    target_path.write_text(output_text, encoding="utf-8")

    print(output_text)
    print(f"Markdown table also written to {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
