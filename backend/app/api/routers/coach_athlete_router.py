"""
Routes coach-athlete : invitations, acceptation, refus, revocation.

Modele :
- 1 coach invite un athlete par email (POST /coach/invite)
- L'athlete (si signup) voit l'invitation et peut accepter/refuser
- Le coach peut revoke a tout moment ses athletes
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.api.routers._shared import security
from app.auth.jwt import get_current_user_id
from app.core.database import get_session
from app.domain.entities.coach_athlete import (
    AthleteSummary,
    CoachAthleteRelation,
    CoachSummary,
    InviteAthleteRequest,
    RelationStatus,
)
from app.domain.entities.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["coach"])


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _user_email(session: Session, user_id: UUID) -> str:
    user = session.get(User, user_id)
    return user.email if user else ""


# ---------- Cote COACH ----------

@router.post(
    "/coach/invite",
    response_model=AthleteSummary,
    status_code=status.HTTP_201_CREATED,
)
def invite_athlete(
    payload: InviteAthleteRequest,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Coach invite un athlete par email. Cree une relation pending."""
    coach_id = UUID(get_current_user_id(token.credentials))
    email = _normalize_email(payload.email)

    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalide")

    coach = db.get(User, coach_id)
    if coach and coach.email == email:
        raise HTTPException(status_code=400, detail="Tu ne peux pas t'inviter toi-meme")

    # Existe deja ?
    existing = db.exec(
        select(CoachAthleteRelation).where(
            CoachAthleteRelation.coach_id == coach_id,
            CoachAthleteRelation.invited_email == email,
        )
    ).first()
    if existing:
        # Si revoked/declined, on re-invite : reset a pending
        if existing.status in (RelationStatus.REVOKED.value, RelationStatus.DECLINED.value):
            existing.status = RelationStatus.PENDING.value
            existing.created_at = datetime.utcnow()
            existing.responded_at = None
            db.add(existing)
            db.commit()
            db.refresh(existing)
            return _to_athlete_summary(db, existing)
        raise HTTPException(status_code=409, detail=f"Invitation deja existante ({existing.status})")

    # Si l'athlete a deja un compte, on lie tout de suite athlete_id
    matched_user = db.exec(select(User).where(User.email == email)).first()

    relation = CoachAthleteRelation(
        coach_id=coach_id,
        athlete_id=matched_user.id if matched_user else None,
        invited_email=email,
        status=RelationStatus.PENDING.value,
    )
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return _to_athlete_summary(db, relation)


@router.get("/coach/athletes", response_model=List[AthleteSummary])
def list_my_athletes(
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Liste les athletes invites par le coach (tous status confondus)."""
    coach_id = UUID(get_current_user_id(token.credentials))
    rows = db.exec(
        select(CoachAthleteRelation)
        .where(CoachAthleteRelation.coach_id == coach_id)
        .order_by(CoachAthleteRelation.created_at.desc())
    ).all()
    return [_to_athlete_summary(db, r) for r in rows]


@router.delete(
    "/coach/athletes/{relation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_athlete(
    relation_id: UUID,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Coach revoque une relation (peu importe son status)."""
    coach_id = UUID(get_current_user_id(token.credentials))
    rel = db.get(CoachAthleteRelation, relation_id)
    if not rel or rel.coach_id != coach_id:
        raise HTTPException(status_code=404, detail="Relation introuvable")
    rel.status = RelationStatus.REVOKED.value
    rel.responded_at = datetime.utcnow()
    db.add(rel)
    db.commit()


# ---------- Cote ATHLETE ----------

@router.get("/athlete/coaches", response_model=List[CoachSummary])
def list_my_coaches(
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Liste les coachs ACCEPTES par l'athlete courant."""
    user_id = UUID(get_current_user_id(token.credentials))
    user = db.get(User, user_id)
    if not user:
        return []

    rows = db.exec(
        select(CoachAthleteRelation).where(
            (CoachAthleteRelation.athlete_id == user_id)
            | (CoachAthleteRelation.invited_email == user.email),
            CoachAthleteRelation.status == RelationStatus.ACCEPTED.value,
        )
    ).all()
    return [_to_coach_summary(db, r) for r in rows]


@router.get("/athlete/invitations", response_model=List[CoachSummary])
def list_my_invitations(
    token=Depends(security),
    db: Session = Depends(get_session),
):
    """Liste les invitations PENDING pour l'athlete courant (par athlete_id OU email)."""
    user_id = UUID(get_current_user_id(token.credentials))
    user = db.get(User, user_id)
    if not user:
        return []

    rows = db.exec(
        select(CoachAthleteRelation).where(
            (CoachAthleteRelation.athlete_id == user_id)
            | (CoachAthleteRelation.invited_email == user.email),
            CoachAthleteRelation.status == RelationStatus.PENDING.value,
        )
    ).all()
    return [_to_coach_summary(db, r) for r in rows]


@router.post(
    "/athlete/invitations/{relation_id}/accept",
    response_model=CoachSummary,
)
def accept_invitation(
    relation_id: UUID,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    rel = _get_my_pending_relation(db, token, relation_id)
    rel.status = RelationStatus.ACCEPTED.value
    rel.responded_at = datetime.utcnow()
    # Lier athlete_id si pas encore fait (cas ou l'invitation a ete cree avant le signup)
    user_id = UUID(get_current_user_id(token.credentials))
    if rel.athlete_id is None:
        rel.athlete_id = user_id
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return _to_coach_summary(db, rel)


@router.post(
    "/athlete/invitations/{relation_id}/decline",
    response_model=CoachSummary,
)
def decline_invitation(
    relation_id: UUID,
    token=Depends(security),
    db: Session = Depends(get_session),
):
    rel = _get_my_pending_relation(db, token, relation_id)
    rel.status = RelationStatus.DECLINED.value
    rel.responded_at = datetime.utcnow()
    user_id = UUID(get_current_user_id(token.credentials))
    if rel.athlete_id is None:
        rel.athlete_id = user_id
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return _to_coach_summary(db, rel)


# ---------- Helpers ----------

def _get_my_pending_relation(
    db: Session, token, relation_id: UUID
) -> CoachAthleteRelation:
    user_id = UUID(get_current_user_id(token.credentials))
    user = db.get(User, user_id)
    rel = db.get(CoachAthleteRelation, relation_id)
    if not rel:
        raise HTTPException(status_code=404, detail="Invitation introuvable")
    is_mine = rel.athlete_id == user_id or (user and rel.invited_email == user.email)
    if not is_mine:
        raise HTTPException(status_code=403, detail="Pas autorise")
    if rel.status != RelationStatus.PENDING.value:
        raise HTTPException(
            status_code=400,
            detail=f"Invitation deja {rel.status}",
        )
    return rel


def _to_athlete_summary(db: Session, rel: CoachAthleteRelation) -> AthleteSummary:
    full_name = None
    if rel.athlete_id:
        u = db.get(User, rel.athlete_id)
        full_name = u.full_name if u else None
    return AthleteSummary(
        relation_id=rel.id,
        athlete_id=rel.athlete_id,
        email=rel.invited_email,
        full_name=full_name,
        status=rel.status,
        created_at=rel.created_at,
        responded_at=rel.responded_at,
    )


def _to_coach_summary(db: Session, rel: CoachAthleteRelation) -> CoachSummary:
    coach = db.get(User, rel.coach_id)
    return CoachSummary(
        relation_id=rel.id,
        coach_id=rel.coach_id,
        coach_email=coach.email if coach else "",
        coach_full_name=coach.full_name if coach else "",
        status=rel.status,
        created_at=rel.created_at,
        responded_at=rel.responded_at,
    )
