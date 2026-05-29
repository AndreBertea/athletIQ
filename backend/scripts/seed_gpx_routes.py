"""Seed du catalogue public de traces GPX (Race Predictor).

Insere 3 traces GPX publiques (`is_public=True`, `user_id=None`) :
  - Swiss Canyon Trail 111K 2026
  - UTMJ 24 - Relais 5 Mouthe-Jougne
  - Trail des Tranchees 2026 - Circuit Poilu

Le Swiss Canyon recoit un attachment PDF "Trace A4 - Swiss Canyon".

Idempotent : reidentifie une route existante par son filename et
remplace ses metadonnees. Les attachments sont aussi remplaces.

Usage :
    python -m scripts.seed_gpx_routes
    # ou
    cd backend && python scripts/seed_gpx_routes.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional
from uuid import UUID, uuid4

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from sqlmodel import Session, create_engine, select  # noqa: E402

from app.domain.entities.gpx_route import GpxAttachment, GpxRoute  # noqa: E402
from app.domain.services.gpx_route_service import compute_gpx_stats  # noqa: E402


CLIENT_APP_DIR = BACKEND_DIR.parent / "client-app"


def _database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    env_path = BACKEND_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == "DATABASE_URL":
                return value.strip().strip('"').strip("'")

    return f"sqlite:///{BACKEND_DIR / 'stridedelta.db'}"


db_engine = create_engine(_database_url(), echo=False, pool_pre_ping=True)


SEED_ROUTES = [
    {
        "name": "Swiss Canyon Trail 111K 2026",
        "filename": "Swiss_Canyon_Trail_111K_2026_2.gpx",
        "source_path": CLIENT_APP_DIR / "Swiss_Canyon_Trail_111K_2026_2.gpx",
        "attachments": [
            {
                "name": "Trace A4 - Swiss Canyon",
                "filename": "Swiss_Canyon_Trail_111K_2026_A4.pdf",
                "source_path": CLIENT_APP_DIR
                / "Page_A4_111K_66cb403a-3d8d-4eaa-a39e-ba52787a207f.pdf",
                "mime_type": "application/pdf",
                "kind": "pdf",
            }
        ],
    },
    {
        "name": "UTMJ 24 - Relais 5 Mouthe-Jougne",
        "filename": "utmj-24-relais-5-mouthe-jougne.gpx",
        "source_path": CLIENT_APP_DIR / "utmj-24-relais-5-mouthe-jougne.gpx",
        "attachments": [],
    },
    {
        "name": "Trail des Tranchees 2026 - Circuit Poilu",
        "filename": "trail-des-tranchees-2026-circuit-poilu.gpx",
        "source_path": CLIENT_APP_DIR / "trail-des-tranchees-2026-circuit-poilu (2).gpx",
        "attachments": [],
    },
]


def _read_bytes(path: Path) -> bytes:
    if not path.exists():
        raise FileNotFoundError(f"Fichier source absent : {path}")
    return path.read_bytes()


def _upsert_route(session: Session, spec: dict) -> GpxRoute:
    existing: Optional[GpxRoute] = session.exec(
        select(GpxRoute).where(
            GpxRoute.filename == spec["filename"],
            GpxRoute.is_public == True,  # noqa: E712
        )
    ).first()

    gpx_bytes = _read_bytes(spec["source_path"])
    distance_km, elevation_gain_m = compute_gpx_stats(gpx_bytes)

    if existing is None:
        route = GpxRoute(
            id=uuid4(),
            user_id=None,
            is_public=True,
            name=spec["name"],
            filename=spec["filename"],
            gpx_data=gpx_bytes,
            distance_km=distance_km,
            elevation_gain_m=elevation_gain_m,
        )
        session.add(route)
        session.flush()
        print(f"  + cree {route.name} ({distance_km:.1f} km, +{elevation_gain_m:.0f} m)")
        return route

    existing.name = spec["name"]
    existing.gpx_data = gpx_bytes
    existing.distance_km = distance_km
    existing.elevation_gain_m = elevation_gain_m
    session.add(existing)
    session.flush()
    print(f"  ~ maj   {existing.name} ({distance_km:.1f} km, +{elevation_gain_m:.0f} m)")
    return existing


def _upsert_attachment(session: Session, route_id: UUID, spec: dict) -> None:
    existing = session.exec(
        select(GpxAttachment).where(
            GpxAttachment.route_id == route_id,
            GpxAttachment.filename == spec["filename"],
        )
    ).first()

    data = _read_bytes(spec["source_path"])

    if existing is None:
        attachment = GpxAttachment(
            id=uuid4(),
            route_id=route_id,
            name=spec["name"],
            filename=spec["filename"],
            mime_type=spec["mime_type"],
            kind=spec["kind"],
            data=data,
        )
        session.add(attachment)
        session.flush()
        print(f"    + attachment {attachment.name} ({len(data) // 1024} ko)")
        return

    existing.name = spec["name"]
    existing.mime_type = spec["mime_type"]
    existing.kind = spec["kind"]
    existing.data = data
    session.add(existing)
    session.flush()
    print(f"    ~ attachment {existing.name} ({len(data) // 1024} ko)")


def main() -> int:
    print("Seed GPX routes (catalogue public)")
    print(f"  DB: {db_engine.url}")
    print(f"  Sources: {CLIENT_APP_DIR}")

    with Session(db_engine) as session:
        for spec in SEED_ROUTES:
            route = _upsert_route(session, spec)
            for attachment_spec in spec["attachments"]:
                _upsert_attachment(session, route.id, attachment_spec)
        session.commit()

    print("Seed termine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
