"""
Routes /gpx-routes : catalogue de traces GPX + attachments associes.

Endpoints :
    GET    /gpx-routes                              -> liste (public + own)
    POST   /gpx-routes                              -> upload (multipart)
    GET    /gpx-routes/{id}                         -> detail + attachments
    GET    /gpx-routes/{id}/content                 -> binaire GPX (download)
    DELETE /gpx-routes/{id}                         -> suppression (owner only)
    POST   /gpx-routes/{id}/attachments             -> upload attachment
    GET    /gpx-routes/{id}/attachments/{att_id}    -> binaire attachment
    DELETE /gpx-routes/{id}/attachments/{att_id}    -> suppression attachment

Les attachments d'une route publique sont uploadables uniquement via le
script de seed (pas d'endpoint admin pour V1) : un POST sur une route
publique renvoie 403.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlmodel import Session

from app.api.routers._shared import security
from app.auth.jwt import get_current_user_id
from app.core.database import get_session
from app.domain.entities.gpx_route import (
    GpxAttachmentRead,
    GpxRouteDetail,
    GpxRouteSummary,
    GpxRouteUserSettingsRead,
    GpxRouteUserSettingsUpdate,
)
from app.domain.services.gpx_route_service import gpx_route_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gpx-routes", tags=["gpx-routes"])


def _summary(route, user_id: UUID, attachment_count: int) -> GpxRouteSummary:
    return GpxRouteSummary(
        id=route.id,
        name=route.name,
        filename=route.filename,
        is_public=route.is_public,
        distance_km=route.distance_km,
        elevation_gain_m=route.elevation_gain_m,
        owned_by_user=route.user_id == user_id,
        attachment_count=attachment_count,
        created_at=route.created_at,
    )


@router.get("", response_model=list[GpxRouteSummary])
def list_routes(
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Liste les traces GPX visibles par l'utilisateur (publiques + own)."""
    user_id = UUID(get_current_user_id(token.credentials))
    routes = gpx_route_service.list_for_user(session, user_id)
    return [
        _summary(
            route,
            user_id,
            gpx_route_service.count_attachments(session, route.id),
        )
        for route in routes
    ]


@router.post("", response_model=GpxRouteSummary, status_code=status.HTTP_201_CREATED)
async def upload_route(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Upload une trace GPX privee (visible uniquement par l'uploader)."""
    user_id = UUID(get_current_user_id(token.credentials))
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nom de fichier requis")
    contents = await file.read()
    try:
        route = gpx_route_service.create_for_user(
            session,
            user_id=user_id,
            name=name or file.filename,
            filename=file.filename,
            gpx_bytes=contents,
            is_public=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _summary(route, user_id, 0)


@router.get("/{route_id}", response_model=GpxRouteDetail)
def get_route_detail(
    route_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    user_id = UUID(get_current_user_id(token.credentials))
    route = gpx_route_service.get_by_id_for_user(session, route_id, user_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route introuvable")
    attachments = gpx_route_service.list_attachments(session, route.id)
    return GpxRouteDetail(
        id=route.id,
        name=route.name,
        filename=route.filename,
        is_public=route.is_public,
        distance_km=route.distance_km,
        elevation_gain_m=route.elevation_gain_m,
        owned_by_user=route.user_id == user_id,
        attachments=[
            GpxAttachmentRead(
                id=att.id,
                route_id=att.route_id,
                name=att.name,
                filename=att.filename,
                mime_type=att.mime_type,
                kind=att.kind,
                created_at=att.created_at,
            )
            for att in attachments
        ],
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


@router.get("/{route_id}/content")
def get_route_content(
    route_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Telecharge le binaire GPX."""
    user_id = UUID(get_current_user_id(token.credentials))
    route = gpx_route_service.get_by_id_for_user(session, route_id, user_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route introuvable")
    return Response(
        content=route.gpx_data,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f"attachment; filename=\"{route.filename}\""},
    )


def _settings_response(settings) -> GpxRouteUserSettingsRead:
    return GpxRouteUserSettingsRead(
        id=settings.id,
        route_id=settings.route_id,
        preferred_engine=settings.preferred_engine,
        analysis_mode=settings.analysis_mode,
        effort_mode=settings.effort_mode,
        ravito_mode=settings.ravito_mode,
        weather_mode=settings.weather_mode,
        manual_temperature_c=settings.manual_temperature_c,
        history_start_date=settings.history_start_date,
        race_datetime=settings.race_datetime,
        custom_ravitos=settings.custom_ravitos or [],
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get("/{route_id}/settings", response_model=GpxRouteUserSettingsRead)
def get_route_settings(
    route_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    user_id = UUID(get_current_user_id(token.credentials))
    settings = gpx_route_service.get_settings_for_user(session, route_id, user_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="Route introuvable")
    return _settings_response(settings)


@router.put("/{route_id}/settings", response_model=GpxRouteUserSettingsRead)
def update_route_settings(
    route_id: UUID,
    payload: GpxRouteUserSettingsUpdate,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    user_id = UUID(get_current_user_id(token.credentials))
    settings = gpx_route_service.update_settings_for_user(
        session,
        route_id,
        user_id,
        payload.model_dump(exclude_unset=True),
    )
    if settings is None:
        raise HTTPException(status_code=404, detail="Route introuvable")
    return _settings_response(settings)


@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_route(
    route_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    """Supprime une route privee (owner only). Les routes publiques ne sont
    pas supprimables via API."""
    user_id = UUID(get_current_user_id(token.credentials))
    deleted = gpx_route_service.delete_for_user(session, route_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Route introuvable ou non supprimable")
    return Response(status_code=204)


@router.post(
    "/{route_id}/attachments",
    response_model=GpxAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    route_id: UUID,
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    kind: Optional[str] = Form(None),
    token=Depends(security),
    session: Session = Depends(get_session),
):
    user_id = UUID(get_current_user_id(token.credentials))
    route = gpx_route_service.get_by_id_for_user(session, route_id, user_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route introuvable")
    if route.is_public or route.user_id != user_id:
        raise HTTPException(status_code=403, detail="Attachment interdit sur cette route")
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nom de fichier requis")
    contents = await file.read()
    detected_kind = (kind or "").strip().lower()
    if not detected_kind:
        lower = file.filename.lower()
        if lower.endswith(".pdf"):
            detected_kind = "pdf"
        elif lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            detected_kind = "image"
        else:
            detected_kind = "other"
    try:
        attachment = gpx_route_service.add_attachment(
            session,
            route_id=route.id,
            name=name or file.filename,
            filename=file.filename,
            mime_type=file.content_type or "application/octet-stream",
            data=contents,
            kind=detected_kind,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return GpxAttachmentRead(
        id=attachment.id,
        route_id=attachment.route_id,
        name=attachment.name,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        kind=attachment.kind,
        created_at=attachment.created_at,
    )


@router.get("/{route_id}/attachments/{attachment_id}")
def get_attachment_content(
    route_id: UUID,
    attachment_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    user_id = UUID(get_current_user_id(token.credentials))
    attachment = gpx_route_service.get_attachment_for_user(
        session, route_id, attachment_id, user_id
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Fichier introuvable")
    return Response(
        content=attachment.data,
        media_type=attachment.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename=\"{attachment.filename}\"",
            "Cache-Control": "private, max-age=600",
        },
    )


@router.delete(
    "/{route_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    route_id: UUID,
    attachment_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
):
    user_id = UUID(get_current_user_id(token.credentials))
    deleted = gpx_route_service.delete_attachment_for_user(
        session, route_id, attachment_id, user_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Fichier introuvable ou non supprimable")
    return Response(status_code=204)
