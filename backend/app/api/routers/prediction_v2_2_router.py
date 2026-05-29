"""
Routes Race Predictor V2.2 (beta) — gestion du profil athletique, des tests
de reference et endpoint de prediction Bayesienne.

Specification : `docs/RACE_PREDICTOR_V2_2_PLAN.md`, section "API cible".

Ce router est sciemment separe de `prediction_router.py` (V1/V2) afin d'eviter
qu'une evolution V2.2 modifie silencieusement les contrats des moteurs precedents.

Endpoints couverts ici :
- GET    /user/me/athletic-profile      (Vague 2)
- PUT    /user/me/athletic-profile      (Vague 2, upsert)
- PATCH  /user/me/athletic-profile      (compatibilite client deja charge)
- GET    /prediction/reference-tests    (Vague 2)
- POST   /prediction/reference-tests    (Vague 2)
- PATCH  /prediction/reference-tests/{id}
- DELETE /prediction/reference-tests/{id} (soft-delete)
- POST   /prediction/v2.2/gpx           (Vague 3 - prediction Bayesienne)
"""
import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.routers._shared import security
from app.domain.services.gpx_route_service import gpx_route_service
from app.auth.jwt import get_current_user_id
from app.core.database import get_session
from app.domain.entities.athletic_profile import (
    ActivityLevel,
    AthleticProfile,
    AthleticSex,
    ExperienceLevel,
    PracticeDominant,
    WeeklyVolumeBand,
)
from app.domain.entities.reference_test import (
    ReferenceTest,
    ReferenceTestQuality,
    ReferenceTestSurface,
    ReferenceTestType,
)
from app.domain.services.race_predictor.v2_2_prediction_service import (
    predict_v2_2,
)
from app.domain.services.race_predictor.v2_3_prediction_service import (
    predict_v2_3,
)
from app.domain.services.race_predictor.v3_prediction_service import predict_v3

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Constantes de validation
# ---------------------------------------------------------------------------

# Plages physiologiques admises pour la taille et le poids (cf. plan V2.2).
HEIGHT_CM_MIN = 120.0
HEIGHT_CM_MAX = 220.0
WEIGHT_KG_MIN = 35.0
WEIGHT_KG_MAX = 200.0

# Anciennete maximale de la date de naissance (annees).
MAX_AGE_YEARS = 100

# Tolerance distance pour les tests route, en proportion.
DISTANCE_TOLERANCE = 0.10  # 10% d'ecart accepte avant warning

# Distance/elevation attendues par type de test (m).
EXPECTED_DISTANCE_M: dict[ReferenceTestType, float] = {
    ReferenceTestType.ROAD_5K: 5_000.0,
    ReferenceTestType.ROAD_10K: 10_000.0,
}
EXPECTED_ELEVATION_M: dict[ReferenceTestType, float] = {
    ReferenceTestType.VERTICAL_KM: 1_000.0,
}


# ---------------------------------------------------------------------------
# Schemas Pydantic (centralisation dans le router, pas de package schemas/ dedie)
# ---------------------------------------------------------------------------


class AthleticProfileResponse(BaseModel):
    """Reponse complete d'un profil athletique."""
    id: UUID
    user_id: UUID
    sex: Optional[AthleticSex] = None
    birth_date: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    activity_level: Optional[ActivityLevel] = None
    experience_level: Optional[ExperienceLevel] = None
    practice_dominant: Optional[PracticeDominant] = None
    weekly_volume_band: Optional[WeeklyVolumeBand] = None
    created_at: datetime
    updated_at: datetime


class AthleticProfileUpsertRequest(BaseModel):
    """
    Body du PUT athletic-profile : tous les champs sont optionnels.

    Permet un upsert : creation si aucun profil n'existe, mise a jour
    partielle sinon (les champs absents conservent leur valeur precedente).
    """
    sex: Optional[AthleticSex] = None
    birth_date: Optional[date] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    activity_level: Optional[ActivityLevel] = None
    experience_level: Optional[ExperienceLevel] = None
    practice_dominant: Optional[PracticeDominant] = None
    weekly_volume_band: Optional[WeeklyVolumeBand] = None


class ReferenceTestResponse(BaseModel):
    """Reponse complete d'un test de reference."""
    id: UUID
    user_id: UUID
    test_type: ReferenceTestType
    performed_at: datetime
    duration_seconds: int
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    temperature_c: Optional[float] = None
    surface: Optional[ReferenceTestSurface] = None
    conditions_notes: Optional[str] = None
    quality_status: ReferenceTestQuality
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = []


class ReferenceTestCreateRequest(BaseModel):
    """Body POST reference-tests : creation d'un test."""
    test_type: ReferenceTestType
    performed_at: datetime
    duration_seconds: int
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    temperature_c: Optional[float] = None
    surface: Optional[ReferenceTestSurface] = None
    conditions_notes: Optional[str] = None
    quality_status: ReferenceTestQuality = ReferenceTestQuality.VALID


class ReferenceTestUpdateRequest(BaseModel):
    """Body PATCH reference-tests : tous les champs optionnels (ex. invalider)."""
    test_type: Optional[ReferenceTestType] = None
    performed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    distance_m: Optional[float] = None
    elevation_gain_m: Optional[float] = None
    temperature_c: Optional[float] = None
    surface: Optional[ReferenceTestSurface] = None
    conditions_notes: Optional[str] = None
    quality_status: Optional[ReferenceTestQuality] = None


# ---------------------------------------------------------------------------
# Helpers de validation
# ---------------------------------------------------------------------------


def _utc_naive(value: datetime) -> datetime:
    """Convertit un datetime aware en datetime naif representant l'instant UTC.

    Convention API : tous les datetime naifs en entree sont supposes deja UTC.
    Pour un datetime aware (avec tzinfo), on convertit explicitement vers UTC
    avant de retirer la tzinfo. La version anterieure utilisait
    ``astimezone(tz=None)`` qui convertit vers le fuseau LOCAL du serveur, ce
    qui faussait toutes les comparaisons temporelles (par exemple comparer
    `performed_at` a `datetime.utcnow()`).

    Reference : `docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md` - R6 partiel, livrable 3.
    """
    if value.tzinfo is None:
        # Convention API : datetime naif = deja UTC, retourne tel quel.
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _validate_profile_fields(payload: AthleticProfileUpsertRequest) -> None:
    """
    Valide les champs physiologiques d'un payload de profil.

    Leve HTTP 400 avec un detail clair en cas de valeur impossible.
    Les enums sont valides automatiquement par Pydantic ; on couvre ici
    les plages numeriques et la coherence temporelle.
    """
    if payload.height_cm is not None and not (HEIGHT_CM_MIN <= payload.height_cm <= HEIGHT_CM_MAX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"height_cm doit etre compris entre {HEIGHT_CM_MIN:.0f} et "
                f"{HEIGHT_CM_MAX:.0f} cm (valeur recue: {payload.height_cm})."
            ),
        )

    if payload.weight_kg is not None and not (WEIGHT_KG_MIN <= payload.weight_kg <= WEIGHT_KG_MAX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"weight_kg doit etre compris entre {WEIGHT_KG_MIN:.0f} et "
                f"{WEIGHT_KG_MAX:.0f} kg (valeur recue: {payload.weight_kg})."
            ),
        )

    if payload.birth_date is not None:
        today = date.today()
        if payload.birth_date > today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="birth_date ne peut pas etre dans le futur.",
            )
        # Age maximal : 100 ans
        earliest_allowed = date(today.year - MAX_AGE_YEARS, today.month, today.day)
        if payload.birth_date < earliest_allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"birth_date ne peut pas etre anterieure a {earliest_allowed.isoformat()} "
                    f"(age max {MAX_AGE_YEARS} ans)."
                ),
            )


def _validate_reference_test_create(payload: ReferenceTestCreateRequest) -> list[str]:
    """
    Valide un payload de creation de test de reference.

    - duration_seconds > 0 (HTTP 400 sinon)
    - performed_at <= maintenant (HTTP 400 sinon)
    - distance / elevation_gain coherentes avec le test_type (warnings non bloquants)

    Retourne la liste de warnings (jamais None).
    """
    warnings: list[str] = []

    if payload.duration_seconds <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"duration_seconds doit etre strictement positif (recu: {payload.duration_seconds}).",
        )

    now = datetime.utcnow()
    normalized_performed = _utc_naive(payload.performed_at)
    if normalized_performed > now + timedelta(minutes=1):
        # +1min de tolerance pour eviter les faux positifs lies aux secondes
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="performed_at ne peut pas etre dans le futur.",
        )

    # Coherence distance attendue (warning seulement, on n'invalide pas)
    expected_distance = EXPECTED_DISTANCE_M.get(payload.test_type)
    if expected_distance is not None and payload.distance_m is not None:
        deviation = abs(payload.distance_m - expected_distance) / expected_distance
        if deviation > DISTANCE_TOLERANCE:
            warnings.append(
                f"distance_m={payload.distance_m:.0f} m s'ecarte de >{DISTANCE_TOLERANCE * 100:.0f}% "
                f"de la valeur attendue {expected_distance:.0f} m pour {payload.test_type.value}; "
                "verifier le protocole."
            )

    # Coherence D+ pour KV
    expected_elevation = EXPECTED_ELEVATION_M.get(payload.test_type)
    if expected_elevation is not None and payload.elevation_gain_m is not None:
        deviation = abs(payload.elevation_gain_m - expected_elevation) / expected_elevation
        if deviation > DISTANCE_TOLERANCE:
            warnings.append(
                f"elevation_gain_m={payload.elevation_gain_m:.0f} m s'ecarte de "
                f">{DISTANCE_TOLERANCE * 100:.0f}% de la valeur attendue {expected_elevation:.0f} m "
                f"pour {payload.test_type.value}; verifier le protocole."
            )

    return warnings


# ---------------------------------------------------------------------------
# Helpers de serialisation
# ---------------------------------------------------------------------------


def _profile_to_response(profile: AthleticProfile) -> AthleticProfileResponse:
    return AthleticProfileResponse(
        id=profile.id,  # type: ignore[arg-type]
        user_id=profile.user_id,
        sex=profile.sex,
        birth_date=profile.birth_date,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        activity_level=profile.activity_level,
        experience_level=profile.experience_level,
        practice_dominant=profile.practice_dominant,
        weekly_volume_band=profile.weekly_volume_band,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _reference_test_to_response(
    test: ReferenceTest,
    *,
    warnings: Optional[list[str]] = None,
) -> ReferenceTestResponse:
    return ReferenceTestResponse(
        id=test.id,  # type: ignore[arg-type]
        user_id=test.user_id,
        test_type=test.test_type,
        performed_at=test.performed_at,
        duration_seconds=test.duration_seconds,
        distance_m=test.distance_m,
        elevation_gain_m=test.elevation_gain_m,
        temperature_c=test.temperature_c,
        surface=test.surface,
        conditions_notes=test.conditions_notes,
        quality_status=test.quality_status,
        created_at=test.created_at,
        updated_at=test.updated_at,
        warnings=warnings or [],
    )


def _get_profile_for_user(session: Session, user_id: UUID) -> Optional[AthleticProfile]:
    return session.exec(
        select(AthleticProfile).where(AthleticProfile.user_id == user_id)
    ).first()


def _get_test_for_user(
    session: Session, user_id: UUID, test_id: UUID
) -> Optional[ReferenceTest]:
    return session.exec(
        select(ReferenceTest).where(
            ReferenceTest.id == test_id,
            ReferenceTest.user_id == user_id,
        )
    ).first()


# ---------------------------------------------------------------------------
# Endpoints : profil athletique
# ---------------------------------------------------------------------------


@router.get(
    "/user/me/athletic-profile",
    response_model=Optional[AthleticProfileResponse],
    tags=["athletic-profile"],
)
async def get_my_athletic_profile(
    token=Depends(security),
    session: Session = Depends(get_session),
) -> Optional[AthleticProfileResponse]:
    """
    Retourne le profil athletique de l'utilisateur courant.

    Un profil est facultatif : `null` est retourne lorsque l'utilisateur n'a
    encore rien renseigne. Ce cas normal ne doit pas produire une erreur
    reseau dans l'interface.
    """
    user_id = UUID(get_current_user_id(token.credentials))
    profile = _get_profile_for_user(session, user_id)
    if profile is None:
        return None
    return _profile_to_response(profile)


@router.put(
    "/user/me/athletic-profile",
    response_model=AthleticProfileResponse,
    tags=["athletic-profile"],
)
@router.patch(
    "/user/me/athletic-profile",
    response_model=AthleticProfileResponse,
    tags=["athletic-profile"],
    include_in_schema=False,
)
async def upsert_my_athletic_profile(
    payload: AthleticProfileUpsertRequest,
    token=Depends(security),
    session: Session = Depends(get_session),
) -> AthleticProfileResponse:
    """
    Cree ou met a jour le profil athletique de l'utilisateur courant.

    Comportement : upsert sur la contrainte unique `user_id`. `PUT` est le
    contrat public ; `PATCH` reste accepte pour les clients frontend charges
    avant la correction du formulaire.
    Tous les champs sont optionnels (`Optional` partout). Les champs absents
    dans le payload preservent la valeur courante en base.

    Validation cote serveur : taille / poids dans des plages physiologiques,
    date de naissance ni future ni anterieure a 100 ans.
    """
    user_id = UUID(get_current_user_id(token.credentials))
    _validate_profile_fields(payload)

    now = datetime.utcnow()
    profile = _get_profile_for_user(session, user_id)

    if profile is None:
        # Creation
        profile = AthleticProfile(
            user_id=user_id,
            sex=payload.sex,
            birth_date=payload.birth_date,
            height_cm=payload.height_cm,
            weight_kg=payload.weight_kg,
            activity_level=payload.activity_level,
            experience_level=payload.experience_level,
            practice_dominant=payload.practice_dominant,
            weekly_volume_band=payload.weekly_volume_band,
            created_at=now,
            updated_at=now,
        )
        session.add(profile)
    else:
        # Mise a jour partielle : on ne touche que les champs effectivement
        # fournis dans le payload (`exclude_unset=True`).
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(profile, field, value)
        profile.updated_at = now

    session.commit()
    session.refresh(profile)
    logger.info("Profil athletique upsert pour user_id=%s", user_id)
    return _profile_to_response(profile)


# ---------------------------------------------------------------------------
# Endpoints : tests de reference
# ---------------------------------------------------------------------------


@router.get(
    "/prediction/reference-tests",
    response_model=list[ReferenceTestResponse],
    tags=["reference-tests"],
)
async def list_reference_tests(
    test_type: Optional[ReferenceTestType] = Query(
        None, description="Filtre optionnel par type de test."
    ),
    include_invalidated: bool = Query(
        False, description="Inclure les tests `invalidated` (defaut : exclus)."
    ),
    token=Depends(security),
    session: Session = Depends(get_session),
) -> list[ReferenceTestResponse]:
    """
    Liste les tests de reference de l'utilisateur courant, tries par
    `performed_at` decroissant.

    - `test_type` : filtre par type de test (cf. enum ReferenceTestType).
    - `include_invalidated` : si false (defaut), les tests soft-deletes
      (`quality_status=invalidated`) sont exclus.
    """
    user_id = UUID(get_current_user_id(token.credentials))
    statement = select(ReferenceTest).where(ReferenceTest.user_id == user_id)
    if test_type is not None:
        statement = statement.where(ReferenceTest.test_type == test_type)
    if not include_invalidated:
        statement = statement.where(
            ReferenceTest.quality_status != ReferenceTestQuality.INVALIDATED
        )
    statement = statement.order_by(ReferenceTest.performed_at.desc())

    tests = session.exec(statement).all()
    return [_reference_test_to_response(t) for t in tests]


@router.post(
    "/prediction/reference-tests",
    response_model=ReferenceTestResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["reference-tests"],
)
async def create_reference_test(
    payload: ReferenceTestCreateRequest,
    token=Depends(security),
    session: Session = Depends(get_session),
) -> ReferenceTestResponse:
    """
    Cree un nouveau test de reference pour l'utilisateur courant.

    Validation cote serveur :
      - duree strictement positive ;
      - date de realisation passee ou actuelle ;
      - distance / D+ coherents avec le `test_type` (warnings non bloquants).

    Le statut qualite par defaut est `valid`. Le service de prediction V2.2
    pourra le degrader en `questionable` ulterieurement (out-of-scope du MVP).
    """
    user_id = UUID(get_current_user_id(token.credentials))
    warnings = _validate_reference_test_create(payload)

    now = datetime.utcnow()
    test = ReferenceTest(
        user_id=user_id,
        test_type=payload.test_type,
        performed_at=_utc_naive(payload.performed_at),
        duration_seconds=payload.duration_seconds,
        distance_m=payload.distance_m,
        elevation_gain_m=payload.elevation_gain_m,
        temperature_c=payload.temperature_c,
        surface=payload.surface,
        conditions_notes=payload.conditions_notes,
        quality_status=payload.quality_status,
        created_at=now,
        updated_at=now,
    )
    session.add(test)
    session.commit()
    session.refresh(test)
    logger.info(
        "Test de reference cree id=%s type=%s user_id=%s",
        test.id,
        test.test_type.value,
        user_id,
    )
    return _reference_test_to_response(test, warnings=warnings)


@router.patch(
    "/prediction/reference-tests/{test_id}",
    response_model=ReferenceTestResponse,
    tags=["reference-tests"],
)
async def patch_reference_test(
    test_id: UUID,
    payload: ReferenceTestUpdateRequest,
    token=Depends(security),
    session: Session = Depends(get_session),
) -> ReferenceTestResponse:
    """
    Met a jour partiellement un test de reference existant.

    Si le test n'appartient pas a l'utilisateur, on retourne 404 (et non 403)
    afin de ne pas reveler l'existence du test a un tiers.

    Champs modifiables courants : `conditions_notes`, `quality_status`,
    `temperature_c`, `surface`, etc.
    """
    user_id = UUID(get_current_user_id(token.credentials))
    test = _get_test_for_user(session, user_id, test_id)
    if test is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test de reference introuvable.",
        )

    update_data = payload.model_dump(exclude_unset=True)

    # Validations sur les champs modifies
    if "duration_seconds" in update_data and update_data["duration_seconds"] is not None:
        if update_data["duration_seconds"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="duration_seconds doit etre strictement positif.",
            )

    if "performed_at" in update_data and update_data["performed_at"] is not None:
        normalized = _utc_naive(update_data["performed_at"])
        if normalized > datetime.utcnow() + timedelta(minutes=1):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="performed_at ne peut pas etre dans le futur.",
            )
        update_data["performed_at"] = normalized

    for field, value in update_data.items():
        setattr(test, field, value)
    test.updated_at = datetime.utcnow()

    session.commit()
    session.refresh(test)
    logger.info("Test de reference mis a jour id=%s user_id=%s", test_id, user_id)
    return _reference_test_to_response(test)


@router.delete(
    "/prediction/reference-tests/{test_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["reference-tests"],
)
async def delete_reference_test(
    test_id: UUID,
    token=Depends(security),
    session: Session = Depends(get_session),
) -> None:
    """
    Soft-delete un test de reference : on bascule `quality_status` a
    `invalidated` afin de preserver l'historique pour le replay
    chronologique du moteur V2.2.

    Retourne 204 No Content en cas de succes. 404 si le test n'existe pas
    ou n'appartient pas a l'utilisateur courant.
    """
    user_id = UUID(get_current_user_id(token.credentials))
    test = _get_test_for_user(session, user_id, test_id)
    if test is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test de reference introuvable.",
        )

    test.quality_status = ReferenceTestQuality.INVALIDATED
    test.updated_at = datetime.utcnow()
    session.commit()
    logger.info("Test de reference invalide (soft-delete) id=%s user_id=%s", test_id, user_id)
    return None


# ---------------------------------------------------------------------------
# Endpoint : POST /prediction/v2.2/gpx (Vague 3 - prediction Bayesienne)
# ---------------------------------------------------------------------------


def _parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO datetime string, returning a UTC-naive value or None.

    Mirrors the helper used by the V1/V2 router so the V2.2 endpoint accepts
    the exact same datetime formats (with or without trailing ``Z``).
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _normalize_effort_mode(effort_mode: Optional[str]) -> str:
    """Normalise the effort mode string to one of {steady, endurance, aggressive}.

    Defaults to ``steady`` for unknown inputs to keep the V2.2 callable from a
    plain HTML form. ``event_intensity_service`` validates the final value.
    """
    if not effort_mode:
        return "steady"
    normalized = effort_mode.strip().lower()
    aliases = {
        "steady": "steady",
        "course_maitrisee": "steady",
        "course maitrisee": "steady",
        "endurance": "endurance",
        "easy": "endurance",
        "aggressive": "aggressive",
        "objectif_agressif": "aggressive",
        "objectif agressif": "aggressive",
    }
    return aliases.get(normalized, "steady")


def _normalize_analysis_mode(analysis_mode: Optional[str]) -> str:
    """Accept ``auto`` / ``trail`` / ``route`` (with a few aliases)."""
    if not analysis_mode:
        return "auto"
    normalized = analysis_mode.strip().lower()
    if normalized in {"auto", "automatic"}:
        return "auto"
    if normalized in {"trail", "trailrun", "trail_run"}:
        return "trail"
    if normalized in {"route", "road", "run"}:
        return "route"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="analysis_mode doit etre auto, trail ou route.",
    )


def _normalize_ravito_mode(ravito_mode: Optional[str]) -> str:
    if not ravito_mode:
        return "auto"
    normalized = ravito_mode.strip().lower()
    if normalized in {"auto", "automatic"}:
        return "auto"
    if normalized in {"manual", "manuel"}:
        return "manual"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="ravito_mode doit etre auto ou manual.",
    )


def _normalize_weather_mode(weather_mode: Optional[str]) -> str:
    if not weather_mode:
        return "auto"
    normalized = weather_mode.strip().lower()
    if normalized in {"auto", "automatic"}:
        return "auto"
    if normalized in {"manual", "manuel"}:
        return "manual"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="weather_mode doit etre auto ou manual.",
    )


def _parse_custom_ravitos_json(custom_ravitos: Optional[str]) -> list[dict[str, Any]]:
    """Decode the optional ``custom_ravitos`` JSON payload.

    The endpoint accepts a JSON array of ``{km, name, pause_min}`` objects.
    Decoding errors fall back to ``[]`` so a malformed manual list does not
    fail the entire prediction; the warning surface comes from the ravito
    pipeline downstream.
    """
    if not custom_ravitos:
        return []
    try:
        parsed = json.loads(custom_ravitos)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_excluded_activity_ids(raw: Optional[str]) -> set[UUID]:
    """Decode the optional ``excluded_activity_ids`` payload.

    Accepts either:
      - a JSON array of UUID strings, or
      - a comma-separated list of UUID strings.

    Unparseable entries are silently dropped (returning ``set()`` rather than
    raising 400 so the endpoint stays forgiving for batch backtest tooling).
    """
    if not raw:
        return set()
    raw = raw.strip()
    if not raw:
        return set()
    candidates: list[str] = []
    if raw.startswith("["):
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            return set()
        if isinstance(decoded, list):
            candidates = [str(item) for item in decoded if item is not None]
    else:
        candidates = [part.strip() for part in raw.split(",") if part.strip()]
    out: set[UUID] = set()
    for candidate in candidates:
        try:
            out.add(UUID(candidate))
        except (ValueError, TypeError):
            continue
    return out


@router.post("/prediction/v2.2/gpx", tags=["prediction-v2.2"])
async def predict_v2_2_from_gpx(
    request: Request,
    response: Response,
    file: UploadFile = File(..., description="Fichier GPX de la course cible"),
    history_start_date: Optional[str] = Form(
        None,
        description=(
            "Date de debut de l'historique (lecture seule en V2.2; conservee "
            "pour compatibilite frontend, l'aggregator V2.2 utilise plutot "
            "`as_of_date` comme borne stricte)."
        ),
    ),
    race_datetime: Optional[str] = Form(
        None, description="Date/heure de la course (UTC)"
    ),
    analysis_mode: Optional[str] = Form(
        "auto", description="Mode d'analyse: auto, trail ou route"
    ),
    effort_mode: Optional[str] = Form(
        "steady", description="Effort cible: steady, endurance ou aggressive"
    ),
    target_heartrate: Optional[float] = Form(
        None, description="FC cible optionnelle"
    ),
    weather_mode: Optional[str] = Form(
        "auto", description="Mode meteo: auto ou manual"
    ),
    temperature_c: Optional[float] = Form(
        None, description="Temperature manuelle en degres Celsius"
    ),
    ravito_mode: Optional[str] = Form(
        "auto", description="Mode ravito: auto ou manual"
    ),
    custom_ravitos: Optional[str] = Form(
        None, description="Ravitos personnalises (JSON array)"
    ),
    as_of_date: Optional[str] = Form(
        None,
        description=(
            "Borne stricte sur les observations (default: utcnow). Tout "
            "evenement >= cette date est ignore. Utile pour les backtests."
        ),
    ),
    excluded_activity_ids: Optional[str] = Form(
        None,
        description=(
            "Activites a exclure (JSON array ou liste separee par virgules). "
            "Sert a empecher une activite cible d'alimenter sa propre prediction."
        ),
    ),
    token=Depends(security),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """DEPRECATED in V2.3.1 - Conserved for benchmark and regression purposes only. New predictions should use /prediction/v2.3/gpx.

    Prediction Race Predictor V2.2 (moteur `v2_2_bayesian`).

    L'endpoint reste fonctionnel afin que les scripts de comparaison
    (`scripts/compare_all_versions.py`) et la validation chronologique
    puissent continuer a appeler V2.2 en mode benchmark. La reponse HTTP
    inclut le header `X-Deprecated-Endpoint: true` et le tableau `warnings`
    contient un message explicite pour le frontend.

    Cf. `docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md` section R6 partiel, livrable 4.

    Pipeline complet (cf. `docs/RACE_PREDICTOR_V2_2_PLAN.md`) :
    1. analyse GPX (segmentation adaptative + smoothing) ;
    2. lecture du profil athletique facultatif ;
    3. calcul des priors populationnels ;
    4. agregation des observations (activites + tests de reference)
       bornees par `as_of_date` ;
    5. update bayesien robuste de chaque parametre latent ;
    6. conversion capacite -> puissance evenement
       (`event_intensity_service.iterate_event_power`) ;
    7. moteur physique V2 inchange (Minetti + meteo + altitude + fatigue) ;
    8. ravitos manuel/auto ;
    9. Monte Carlo enrichi par les variances posterior.

    Retourne la reponse V2.2 complete incluant `athlete_model`,
    `event_intensity` et un `debug_trace` traceable pour la sauvegarde.
    """
    # Signaler la depreciation au client via header HTTP (cf. R6 partiel,
    # livrable 4). L'endpoint reste fonctionnel pour les comparaisons.
    response.headers["X-Deprecated-Endpoint"] = "true"

    user_id = UUID(get_current_user_id(token.credentials))

    # FIX 6b (V2.3.1) : bloquer l'usage interactif de V2.2.
    # V2.2 est scientifiquement invalide comme moteur utilisateur (cf.
    # benchmark UTMJ +60.9 %). On refuse toute requete depuis l'UI utilisateur
    # (410 Gone) tout en preservant les scripts de benchmark/regression qui
    # peuvent passer le header ``X-Source: benchmark`` pour bypass. Le
    # benchmark principal ``scripts/compare_all_versions.py`` appelle
    # ``predict_v2_2`` en import direct et n'est donc pas affecte.
    benchmark_marker = request.headers.get("X-Source")
    if benchmark_marker != "benchmark":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "V2.2 endpoint is deprecated for interactive use. "
                "New predictions must use /api/v1/prediction/v2.3/gpx. "
                "Benchmark/regression scripts can pass header "
                "'X-Source: benchmark' to bypass."
            ),
        )

    # --- 1. Lire et decoder le contenu GPX -----------------------------------
    try:
        gpx_bytes = await file.read()
        gpx_text = gpx_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fichier GPX invalide (encodage non UTF-8): {exc}",
        ) from exc

    # --- 2. Normaliser les parametres ---------------------------------------
    resolved_analysis_mode = _normalize_analysis_mode(analysis_mode)
    resolved_effort_mode = _normalize_effort_mode(effort_mode)
    resolved_ravito_mode = _normalize_ravito_mode(ravito_mode)
    resolved_weather_mode = _normalize_weather_mode(weather_mode)
    parsed_race_datetime = _parse_optional_datetime(race_datetime)
    parsed_as_of_date = _parse_optional_datetime(as_of_date) or datetime.utcnow()
    custom_ravitos_data = _parse_custom_ravitos_json(custom_ravitos)
    excluded_ids = _parse_excluded_activity_ids(excluded_activity_ids)

    # --- 3. Executer la prediction V2.2 -------------------------------------
    # GPX parsing errors come from `gpxpy` as `GPXXMLSyntaxException`, which
    # is not a `ValueError`. We catch it explicitly so the endpoint returns
    # 400 instead of 500 when the uploaded file is not a valid GPX document.
    try:
        from gpxpy.gpx import GPXException, GPXXMLSyntaxException  # type: ignore
    except ImportError:  # pragma: no cover - gpxpy is a hard dep, but stay safe
        GPXException = Exception  # type: ignore
        GPXXMLSyntaxException = Exception  # type: ignore

    try:
        result = predict_v2_2(
            session,
            user_id,
            gpx_text,
            race_datetime=parsed_race_datetime,
            effort_mode=resolved_effort_mode,
            analysis_mode=resolved_analysis_mode,
            target_heartrate=target_heartrate,
            weather_mode=resolved_weather_mode,
            manual_temperature_c=temperature_c,
            ravito_mode=resolved_ravito_mode,
            custom_ravitos=custom_ravitos_data,
            as_of_date=parsed_as_of_date,
            excluded_activity_ids=excluded_ids,
            filename=file.filename,
        )
    except (ValueError, GPXXMLSyntaxException, GPXException) as exc:
        # GPX vide / GPX sans trace exploitable / parametres incoherents.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GPX invalide ou parametres incoherents: {exc}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Erreur prediction V2.2: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur prediction V2.2: {exc}",
        ) from exc

    # Copie informative pour les clients qui veulent rejouer la prediction.
    if history_start_date:
        result["history_start_date"] = history_start_date

    # Avertissement de depreciation V2.3.1 - cf. R6 partiel livrable 4.
    # Conserve dans `result["warnings"]` afin que le frontend puisse afficher
    # un bandeau utilisateur sans modifier le contrat de reponse.
    deprecation_warning = (
        "DEPRECATED: V2.2 engine is conserved for benchmark only. "
        "Use V2.3.1 for new predictions."
    )
    if isinstance(result, dict):
        warnings_field = result.get("warnings")
        if isinstance(warnings_field, list):
            if deprecation_warning not in warnings_field:
                warnings_field.append(deprecation_warning)
        else:
            result["warnings"] = [deprecation_warning]

    return result


# ---------------------------------------------------------------------------
# Endpoint : POST /prediction/v2.3/gpx (Race Predictor V2.3 - sans double
# comptage Daniels). V2.2 et V2.3 cohabitent dans ce router.
# ---------------------------------------------------------------------------


@router.post("/prediction/v2.3/gpx", tags=["prediction-v2.3"])
async def predict_v2_3_from_gpx(
    file: UploadFile = File(..., description="Fichier GPX de la course cible"),
    history_start_date: Optional[str] = Form(
        None,
        description=(
            "Borne inferieure stricte sur les observations. Si None, default "
            "= as_of_date - 3 ans (conforme R1). Activites et tests anterieurs "
            "a cette date sont ignores par l'aggregator."
        ),
    ),
    race_datetime: Optional[str] = Form(
        None, description="Date/heure de la course (UTC)"
    ),
    analysis_mode: Optional[str] = Form(
        "auto", description="Mode d'analyse: auto, trail ou route"
    ),
    effort_mode: Optional[str] = Form(
        "steady", description="Effort cible: steady, endurance ou aggressive"
    ),
    target_heartrate: Optional[float] = Form(
        None, description="FC cible optionnelle"
    ),
    weather_mode: Optional[str] = Form(
        "auto", description="Mode meteo: auto ou manual"
    ),
    temperature_c: Optional[float] = Form(
        None, description="Temperature manuelle en degres Celsius"
    ),
    ravito_mode: Optional[str] = Form(
        "auto", description="Mode ravito: auto ou manual"
    ),
    custom_ravitos: Optional[str] = Form(
        None, description="Ravitos personnalises (JSON array)"
    ),
    as_of_date: Optional[str] = Form(
        None,
        description=(
            "Borne stricte sur les observations (default: utcnow). Tout "
            "evenement >= cette date est ignore. Utile pour les backtests."
        ),
    ),
    excluded_activity_ids: Optional[str] = Form(
        None,
        description=(
            "Activites a exclure (JSON array ou liste separee par virgules). "
            "Sert a empecher une activite cible d'alimenter sa propre prediction."
        ),
    ),
    token=Depends(security),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Prediction Race Predictor V2.3.1 (moteur `v2_3_1_bayesian`).

    V2.3.1 reprend la calibration directe historique de V2 (pas d'inversion
    Daniels) et la combine avec la couche bayesienne de V2.2 (prior
    populationnel, robust_updater, Monte Carlo enrichi). Cf.
    `docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md` section R4.

    Pipeline simplifie par rapport a V2.2 :
    1. analyse GPX (segmentation adaptative) ;
    2. lecture profil athletique facultatif ;
    3. calcul prior populationnel (P_run en W/kg directement) ;
    4. agregation observations (cle `p_run_wkg` apres refactor agent V1) ;
    5. update bayesien robuste ;
    6. PAS d'iteration capacity -> event_power. P_run posterior est branche
       DIRECTEMENT sur le moteur physique V2 ;
    7. ravitos + Monte Carlo + reponse JSON.

    Notes V2.3.1 (R4) :
    - L'engine_version retourne est ``v2_3_1_bayesian``, defini directement
      par la constante ``ENGINE_VERSION`` du service
      ``v2_3_prediction_service``. Le router ne le surcharge plus (FIX 3
      post-audit V2.3.1).
    - ``target_heartrate`` est conserve dans le contrat API mais n'est pas
      encore consomme par le moteur V2.3.1. Un warning explicite est emis si
      le client envoie ce champ.
    - Les anciennes predictions sauvegardees avec ``engine_version =
      v2_3_bayesian`` restent lisibles sans migration retroactive.
    """
    user_id = UUID(get_current_user_id(token.credentials))

    # --- 1. Lire et decoder le contenu GPX -----------------------------------
    try:
        gpx_bytes = await file.read()
        gpx_text = gpx_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Fichier GPX invalide (encodage non UTF-8): {exc}",
        ) from exc

    # --- 2. Normaliser les parametres ---------------------------------------
    resolved_analysis_mode = _normalize_analysis_mode(analysis_mode)
    resolved_effort_mode = _normalize_effort_mode(effort_mode)
    resolved_ravito_mode = _normalize_ravito_mode(ravito_mode)
    resolved_weather_mode = _normalize_weather_mode(weather_mode)
    parsed_race_datetime = _parse_optional_datetime(race_datetime)
    parsed_as_of_date = _parse_optional_datetime(as_of_date) or datetime.utcnow()
    # FIX 1 (V2.3.1) : history_start_date doit etre transmis au service.
    # La V2.3 ignorait silencieusement ce parametre; R1 l'applique reellement
    # dans l'aggregator. Si None, le service applique le default 3 ans.
    parsed_history_start_date = _parse_optional_datetime(history_start_date)
    custom_ravitos_data = _parse_custom_ravitos_json(custom_ravitos)
    excluded_ids = _parse_excluded_activity_ids(excluded_activity_ids)

    # --- 3. Executer la prediction V2.3 -------------------------------------
    try:
        from gpxpy.gpx import GPXException, GPXXMLSyntaxException  # type: ignore
    except ImportError:  # pragma: no cover - gpxpy is a hard dep, but stay safe
        GPXException = Exception  # type: ignore
        GPXXMLSyntaxException = Exception  # type: ignore

    try:
        result = predict_v2_3(
            session,
            user_id,
            gpx_text,
            race_datetime=parsed_race_datetime,
            effort_mode=resolved_effort_mode,
            analysis_mode=resolved_analysis_mode,
            target_heartrate=target_heartrate,
            weather_mode=resolved_weather_mode,
            manual_temperature_c=temperature_c,
            ravito_mode=resolved_ravito_mode,
            custom_ravitos=custom_ravitos_data,
            as_of_date=parsed_as_of_date,
            excluded_activity_ids=excluded_ids,
            history_start_date=parsed_history_start_date,
            filename=file.filename,
        )
    except (ValueError, GPXXMLSyntaxException, GPXException) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GPX invalide ou parametres incoherents: {exc}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Erreur prediction V2.3: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur prediction V2.3: {exc}",
        ) from exc

    # Copie informative pour les clients qui veulent rejouer la prediction.
    if history_start_date:
        result["history_start_date"] = history_start_date

    # FIX 3 (V2.3.1) : l'override d'engine_version qui transformait
    # ``v2_3_bayesian`` en ``v2_3_1_bayesian`` cote router a ete supprime.
    # La constante ENGINE_VERSION du service vaut directement
    # ``v2_3_1_bayesian``, donc le resultat sortant porte deja la bonne
    # etiquette dans ``engine_version``, ``calibration.engine_version`` et
    # ``debug_trace.engine_version``. Cf. docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md
    # section R4 livrable 2.

    # --- R4 : warning explicite si target_heartrate est envoye.
    # Le champ est conserve dans le contrat API pour anticiper le lot futur
    # (strategie de course a FC cible), mais le moteur V2.3.1 ne le consomme
    # pas encore. Le frontend ne doit pas le proposer dans l'UI V2.3.
    if target_heartrate is not None:
        warnings_field = result.get("warnings")
        warning_message = (
            "target_heartrate received but not yet consumed by V2.3.1 engine"
        )
        if isinstance(warnings_field, list):
            if warning_message not in warnings_field:
                warnings_field.append(warning_message)
        else:
            result["warnings"] = [warning_message]

    return result


@router.post("/prediction/v3/gpx", tags=["prediction-v3"])
async def predict_v3_from_gpx(
    file: Optional[UploadFile] = File(None, description="Fichier GPX de la course cible"),
    route_id: Optional[str] = Form(None, description="Identifiant d'une trace deja enregistree"),
    history_start_date: Optional[str] = Form(None),
    race_datetime: Optional[str] = Form(None),
    analysis_mode: Optional[str] = Form("auto"),
    effort_mode: Optional[str] = Form("steady"),
    target_heartrate: Optional[float] = Form(None),
    weather_mode: Optional[str] = Form("auto"),
    temperature_c: Optional[float] = Form(None),
    ravito_mode: Optional[str] = Form("auto"),
    custom_ravitos: Optional[str] = Form(None),
    as_of_date: Optional[str] = Form(None),
    excluded_activity_ids: Optional[str] = Form(None),
    token=Depends(security),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Prediction V3: V2.3.1 physique avec preuve Garmin sparse ponderee.

    Accepte soit un upload direct (`file`), soit une trace deja enregistree
    en base via `route_id` (catalogue public ou import perso).

    Le correcteur residuel de type RF est presente dans le contrat de
    reponse, mais reste desactive tant qu'un ensemble de references validees
    n'a pas permis son apprentissage et sa validation.
    """
    user_id = UUID(get_current_user_id(token.credentials))
    if route_id:
        try:
            route_uuid = UUID(route_id)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail="route_id invalide") from exc
        route = gpx_route_service.get_by_id_for_user(session, route_uuid, user_id)
        if route is None:
            raise HTTPException(status_code=404, detail="Trace GPX introuvable")
        try:
            gpx_text = bytes(route.gpx_data).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GPX corrompu en base: {exc}",
            ) from exc
        gpx_filename = route.filename
    elif file is not None and file.filename:
        try:
            gpx_text = (await file.read()).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Fichier GPX invalide (encodage non UTF-8): {exc}",
            ) from exc
        gpx_filename = file.filename
    else:
        raise HTTPException(status_code=400, detail="file ou route_id requis")

    parsed_race_datetime = _parse_optional_datetime(race_datetime)
    parsed_as_of_date = _parse_optional_datetime(as_of_date) or datetime.utcnow()
    parsed_history_start_date = _parse_optional_datetime(history_start_date)
    try:
        result = predict_v3(
            session,
            user_id,
            gpx_text,
            race_datetime=parsed_race_datetime,
            effort_mode=_normalize_effort_mode(effort_mode),
            analysis_mode=_normalize_analysis_mode(analysis_mode),
            target_heartrate=target_heartrate,
            weather_mode=_normalize_weather_mode(weather_mode),
            manual_temperature_c=temperature_c,
            ravito_mode=_normalize_ravito_mode(ravito_mode),
            custom_ravitos=_parse_custom_ravitos_json(custom_ravitos),
            as_of_date=parsed_as_of_date,
            excluded_activity_ids=_parse_excluded_activity_ids(excluded_activity_ids),
            history_start_date=parsed_history_start_date,
            filename=gpx_filename,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GPX invalide ou parametres incoherents: {exc}",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception("Erreur prediction V3: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur prediction V3: {exc}",
        ) from exc

    if history_start_date:
        result["history_start_date"] = history_start_date
    if target_heartrate is not None:
        result.setdefault("warnings", []).append(
            "target_heartrate received but not yet consumed by V3 engine"
        )
    return result
