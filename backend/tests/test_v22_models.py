"""
Tests de la couche donnees Race Predictor V2.2

Couvre les nouvelles entites `AthleticProfile` et `ReferenceTest` :
  - creation/persistance basique sur SQLite in-memory ;
  - contrainte d'unicite sur AthleticProfile.user_id ;
  - autorisation de plusieurs ReferenceTest par utilisateur ;
  - facultativite de tous les champs sauf id + user_id pour le profil.

Le fixture isole chaque test dans sa propre base in-memory : aucun effet
de bord sur la base de developpement, aucune dependance Alembic.
"""
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

# Import toutes les entites du domaine pour que SQLModel.metadata soit
# complet (les FK pointent vers `user.id`, donc la table user doit etre creee).
from app.domain.entities import (  # noqa: F401 - side-effect: enregistre les metadonnees
    Activity,
    AthleticProfile,
    AthleticSex,
    ActivityLevel,
    ExperienceLevel,
    PracticeDominant,
    ReferenceTest,
    ReferenceTestQuality,
    ReferenceTestSurface,
    ReferenceTestType,
    User,
    WeeklyVolumeBand,
)


@pytest.fixture()
def session() -> Session:
    """Session SQLModel sur une base SQLite in-memory toute fraiche."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _make_user(session: Session, email: str = "user@example.com") -> User:
    """Cree un utilisateur minimal et le persiste."""
    user = User(
        email=email,
        full_name="Test User",
        hashed_password="not-a-real-hash",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_athletic_profile_table_creates_and_persists(session: Session) -> None:
    user = _make_user(session)
    profile = AthleticProfile(
        user_id=user.id,
        sex=AthleticSex.MALE,
        birth_date=date(1992, 6, 15),
        height_cm=180.0,
        weight_kg=72.5,
        activity_level=ActivityLevel.ACTIVE,
        experience_level=ExperienceLevel.REGULAR,
        practice_dominant=PracticeDominant.TRAIL,
        weekly_volume_band=WeeklyVolumeBand.BAND_40_60KM,
    )
    session.add(profile)
    session.commit()

    fetched = session.exec(
        select(AthleticProfile).where(AthleticProfile.user_id == user.id)
    ).one()

    assert fetched.id == profile.id
    assert fetched.sex == AthleticSex.MALE
    assert fetched.birth_date == date(1992, 6, 15)
    assert fetched.height_cm == pytest.approx(180.0)
    assert fetched.weight_kg == pytest.approx(72.5)
    assert fetched.activity_level == ActivityLevel.ACTIVE
    assert fetched.experience_level == ExperienceLevel.REGULAR
    assert fetched.practice_dominant == PracticeDominant.TRAIL
    assert fetched.weekly_volume_band == WeeklyVolumeBand.BAND_40_60KM
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_reference_test_table_creates_and_persists(session: Session) -> None:
    user = _make_user(session)
    performed = datetime(2026, 4, 1, 9, 30, 0)
    test_row = ReferenceTest(
        user_id=user.id,
        test_type=ReferenceTestType.ROAD_10K,
        performed_at=performed,
        duration_seconds=2400,
        distance_m=10000.0,
        elevation_gain_m=20.0,
        temperature_c=14.5,
        surface=ReferenceTestSurface.ASPHALT,
        conditions_notes="Parcours plat, sans vent.",
        quality_status=ReferenceTestQuality.VALID,
    )
    session.add(test_row)
    session.commit()

    fetched = session.exec(
        select(ReferenceTest).where(ReferenceTest.user_id == user.id)
    ).one()

    assert fetched.id == test_row.id
    assert fetched.test_type == ReferenceTestType.ROAD_10K
    assert fetched.performed_at == performed
    assert fetched.duration_seconds == 2400
    assert fetched.distance_m == pytest.approx(10000.0)
    assert fetched.elevation_gain_m == pytest.approx(20.0)
    assert fetched.temperature_c == pytest.approx(14.5)
    assert fetched.surface == ReferenceTestSurface.ASPHALT
    assert fetched.conditions_notes == "Parcours plat, sans vent."
    assert fetched.quality_status == ReferenceTestQuality.VALID


def test_athletic_profile_unique_constraint_on_user_id(session: Session) -> None:
    user = _make_user(session)
    session.add(AthleticProfile(user_id=user.id))
    session.commit()

    duplicate = AthleticProfile(user_id=user.id)
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_reference_test_multiple_tests_per_user_allowed(session: Session) -> None:
    user = _make_user(session)
    base = datetime(2026, 1, 15, 8, 0, 0)
    tests = [
        ReferenceTest(
            user_id=user.id,
            test_type=ReferenceTestType.ROAD_5K,
            performed_at=base,
            duration_seconds=1100,
        ),
        ReferenceTest(
            user_id=user.id,
            test_type=ReferenceTestType.ROAD_10K,
            performed_at=base + timedelta(days=14),
            duration_seconds=2300,
        ),
        ReferenceTest(
            user_id=user.id,
            test_type=ReferenceTestType.LONG_STEADY,
            performed_at=base + timedelta(days=28),
            duration_seconds=6300,
        ),
    ]
    for t in tests:
        session.add(t)
    session.commit()

    stored = session.exec(
        select(ReferenceTest).where(ReferenceTest.user_id == user.id)
    ).all()
    assert len(stored) == 3
    assert {t.test_type for t in stored} == {
        ReferenceTestType.ROAD_5K,
        ReferenceTestType.ROAD_10K,
        ReferenceTestType.LONG_STEADY,
    }


def test_athletic_profile_all_fields_nullable_except_id_and_user(
    session: Session,
) -> None:
    user = _make_user(session)
    profile = AthleticProfile(user_id=user.id)
    session.add(profile)
    session.commit()

    fetched = session.exec(
        select(AthleticProfile).where(AthleticProfile.user_id == user.id)
    ).one()
    assert fetched.id is not None
    assert fetched.user_id == user.id
    assert fetched.sex is None
    assert fetched.birth_date is None
    assert fetched.height_cm is None
    assert fetched.weight_kg is None
    assert fetched.activity_level is None
    assert fetched.experience_level is None
    assert fetched.practice_dominant is None
    assert fetched.weekly_volume_band is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
