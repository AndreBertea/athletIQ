"""
GpxRouteService - couche metier pour le catalogue de traces GPX.

Visibilite : un user voit toutes les routes `is_public=True` + ses propres
routes (`user_id == self`). Toute autre route renvoie 404.

Parsing GPX : utilise gpxpy (deja dans requirements) pour calculer la
distance totale et le denivele positif. En cas de fichier invalide, leve
ValueError pour que le router renvoie 400.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Query
from sqlmodel import Session, select

from app.domain.entities.gpx_route import GpxAttachment, GpxRoute, GpxRouteUserSettings


_EARTH_RADIUS_M = 6_371_000.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _EARTH_RADIUS_M * c


def compute_gpx_stats(gpx_bytes: bytes) -> Tuple[Optional[float], Optional[float]]:
    """Retourne (distance_km, elevation_gain_m) ou (None, None) si parse KO."""
    try:
        import gpxpy  # type: ignore

        text = gpx_bytes.decode("utf-8", errors="replace")
        gpx = gpxpy.parse(text)
    except Exception:
        return (None, None)

    total_m = 0.0
    gain_m = 0.0
    previous_point = None
    previous_elev = None
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                if previous_point is not None:
                    total_m += _haversine_m(
                        previous_point.latitude,
                        previous_point.longitude,
                        point.latitude,
                        point.longitude,
                    )
                if point.elevation is not None and previous_elev is not None:
                    delta = point.elevation - previous_elev
                    if delta > 0:
                        gain_m += delta
                previous_point = point
                if point.elevation is not None:
                    previous_elev = point.elevation
    if total_m <= 0:
        return (None, None)
    return (total_m / 1000.0, gain_m)


class GpxRouteService:
    """Service applicatif sur les routes GPX."""

    @staticmethod
    def list_for_user(session: Session, user_id: UUID) -> list[GpxRoute]:
        statement = (
            select(GpxRoute)
            .where((GpxRoute.is_public == True) | (GpxRoute.user_id == user_id))  # noqa: E712
            .order_by(GpxRoute.is_public.desc(), GpxRoute.name.asc())
        )
        return list(session.exec(statement).all())

    @staticmethod
    def get_by_id_for_user(
        session: Session, route_id: UUID, user_id: UUID
    ) -> Optional[GpxRoute]:
        route = session.get(GpxRoute, route_id)
        if route is None:
            return None
        if not route.is_public and route.user_id != user_id:
            return None
        return route

    @staticmethod
    def count_attachments(session: Session, route_id: UUID) -> int:
        statement = select(GpxAttachment).where(GpxAttachment.route_id == route_id)
        return len(list(session.exec(statement).all()))

    @staticmethod
    def list_attachments(session: Session, route_id: UUID) -> list[GpxAttachment]:
        statement = (
            select(GpxAttachment)
            .where(GpxAttachment.route_id == route_id)
            .order_by(GpxAttachment.created_at.asc())
        )
        return list(session.exec(statement).all())

    @staticmethod
    def get_attachment_for_user(
        session: Session,
        route_id: UUID,
        attachment_id: UUID,
        user_id: UUID,
    ) -> Optional[GpxAttachment]:
        route = GpxRouteService.get_by_id_for_user(session, route_id, user_id)
        if route is None:
            return None
        attachment = session.get(GpxAttachment, attachment_id)
        if attachment is None or attachment.route_id != route_id:
            return None
        return attachment

    @staticmethod
    def get_settings_for_user(
        session: Session,
        route_id: UUID,
        user_id: UUID,
    ) -> Optional[GpxRouteUserSettings]:
        route = GpxRouteService.get_by_id_for_user(session, route_id, user_id)
        if route is None:
            return None
        statement = select(GpxRouteUserSettings).where(
            GpxRouteUserSettings.route_id == route_id,
            GpxRouteUserSettings.user_id == user_id,
        )
        settings = session.exec(statement).first()
        if settings is not None:
            return settings

        settings = GpxRouteUserSettings(user_id=user_id, route_id=route_id)
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings

    @staticmethod
    def update_settings_for_user(
        session: Session,
        route_id: UUID,
        user_id: UUID,
        values: dict,
    ) -> Optional[GpxRouteUserSettings]:
        settings = GpxRouteService.get_settings_for_user(session, route_id, user_id)
        if settings is None:
            return None

        allowed = {
            "preferred_engine",
            "analysis_mode",
            "effort_mode",
            "ravito_mode",
            "weather_mode",
            "manual_temperature_c",
            "history_start_date",
            "race_datetime",
            "custom_ravitos",
        }
        nullable_allowed = {"manual_temperature_c", "history_start_date", "race_datetime"}
        for key, value in values.items():
            if key not in allowed:
                continue
            if value is None and key not in nullable_allowed:
                continue
            setattr(settings, key, value)
        settings.updated_at = datetime.utcnow()
        session.add(settings)
        session.commit()
        session.refresh(settings)
        return settings

    @staticmethod
    def create_for_user(
        session: Session,
        user_id: UUID,
        name: str,
        filename: str,
        gpx_bytes: bytes,
        *,
        is_public: bool = False,
    ) -> GpxRoute:
        if not gpx_bytes:
            raise ValueError("Fichier GPX vide")
        distance_km, elevation_gain_m = compute_gpx_stats(gpx_bytes)
        if distance_km is None:
            raise ValueError("Fichier GPX invalide ou sans trace exploitable")

        route = GpxRoute(
            user_id=None if is_public else user_id,
            is_public=is_public,
            name=name.strip() or filename,
            filename=filename,
            gpx_data=gpx_bytes,
            distance_km=distance_km,
            elevation_gain_m=elevation_gain_m,
        )
        session.add(route)
        session.commit()
        session.refresh(route)
        return route

    @staticmethod
    def delete_for_user(session: Session, route_id: UUID, user_id: UUID) -> bool:
        route = session.get(GpxRoute, route_id)
        if route is None:
            return False
        if route.is_public or route.user_id != user_id:
            return False
        attachments = session.exec(
            select(GpxAttachment).where(GpxAttachment.route_id == route_id)
        ).all()
        for attachment in attachments:
            session.delete(attachment)
        session.delete(route)
        session.commit()
        return True

    @staticmethod
    def add_attachment(
        session: Session,
        route_id: UUID,
        name: str,
        filename: str,
        mime_type: str,
        data: bytes,
        kind: str = "other",
    ) -> GpxAttachment:
        if not data:
            raise ValueError("Fichier joint vide")
        attachment = GpxAttachment(
            route_id=route_id,
            name=name.strip() or filename,
            filename=filename,
            mime_type=mime_type or "application/octet-stream",
            kind=kind,
            data=data,
        )
        session.add(attachment)
        session.commit()
        session.refresh(attachment)
        return attachment

    @staticmethod
    def delete_attachment_for_user(
        session: Session,
        route_id: UUID,
        attachment_id: UUID,
        user_id: UUID,
    ) -> bool:
        attachment = GpxRouteService.get_attachment_for_user(
            session, route_id, attachment_id, user_id
        )
        if attachment is None:
            return False
        route = session.get(GpxRoute, route_id)
        if route is None:
            return False
        if route.is_public or route.user_id != user_id:
            return False
        session.delete(attachment)
        session.commit()
        return True


gpx_route_service = GpxRouteService()
