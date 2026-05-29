"""R6 final (V2.3.1) blocking tests.

Verifie les acquis du lot R6 final du plan
``docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md`` :

1. ``prediction_router.py`` ne contient plus de DDL runtime pour la colonne
   ``engine_version`` (ALTER TABLE / CREATE INDEX au demarrage de l'app).
   La colonne est desormais geree exclusivement par la migration Alembic
   ``v231_engine_version_add_engine_version_to_raceprediction.py``.
2. La colonne ``engine_version`` est presente dans la DB SQLite locale du
   backend (verification "bout en bout" sur l'installation developpeur :
   apres migration Alembic, la colonne reste presente sans DDL runtime).
3. L'adaptateur ``_flat_capacity_observations_compat`` de V2.2 reconnait
   les 3 clefs publiees par les differents agregateurs : la cle V2.3.1
   post-R1 ``p_ref_steady_wkg``, la cle legacy V2.3 ``p_run_wkg``, et la
   cle historique V2.2 ``flat_capacity_mps``. Ce verrouillage garantit
   que V2.2 reste appelable comme moteur de benchmark/comparaison meme
   apres la separation R1 ``p_ref_steady_wkg`` / ``p_capacity_test_wkg``.

La conversion W/kg -> m/s utilise le cout plat Minetti
``MINETTI_FLAT_COST_J_PER_KG_M ~= 3.6 J/(kg.m)`` :
``flat_capacity_mps = p_run_wkg / MINETTI_FLAT_COST_J_PER_KG_M``.
"""
from __future__ import annotations

import pathlib

import pytest

from app.domain.services.race_predictor.v2_2_prediction_service import (
    MINETTI_FLAT_COST_J_PER_KG_M,
    _flat_capacity_observations_compat,
)


# -- Sentinelles file paths ---------------------------------------------------

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
PREDICTION_ROUTER_PATH = (
    BACKEND_ROOT / "app" / "api" / "routers" / "prediction_router.py"
)
LOCAL_SQLITE_DB_PATH = BACKEND_ROOT / "stridedelta.db"


# -- 1. DDL runtime supprime du router ---------------------------------------


def test_no_ddl_runtime_engine_version_in_prediction_router():
    """``prediction_router.py`` ne doit plus contenir de DDL runtime
    pour la colonne ``engine_version`` (ALTER TABLE) ni pour son index
    (CREATE INDEX IF NOT EXISTS). La gestion releve uniquement de la
    migration Alembic ``v231_engine_version``.
    """
    source = PREDICTION_ROUTER_PATH.read_text(encoding="utf-8")
    assert (
        "ALTER TABLE raceprediction ADD COLUMN engine_version" not in source
    ), (
        "Le router contient encore le DDL runtime ALTER TABLE engine_version. "
        "Cette manipulation doit etre supprimee : la migration Alembic "
        "`v231_engine_version` s'en charge desormais."
    )
    assert (
        "CREATE INDEX IF NOT EXISTS ix_raceprediction_engine_version"
        not in source
    ), (
        "Le router contient encore le DDL runtime CREATE INDEX IF NOT EXISTS "
        "ix_raceprediction_engine_version. Cette manipulation doit etre "
        "supprimee : la migration Alembic `v231_engine_version` s'en charge."
    )


# -- 2. Colonne engine_version presente cote DB locale -----------------------


def test_engine_version_column_exists_via_migration():
    """La colonne ``engine_version`` doit etre presente dans la DB SQLite
    locale du backend, demontrant qu'elle subsiste sans le DDL runtime
    (mise en place par la migration Alembic
    ``v231_engine_version_add_engine_version_to_raceprediction``).
    """
    if not LOCAL_SQLITE_DB_PATH.exists():
        pytest.skip(
            "DB locale absente (stridedelta.db) - test ignore en environnement "
            "neuf ; la migration Alembic restera responsable de la colonne."
        )

    from sqlalchemy import create_engine, inspect

    engine = create_engine(f"sqlite:///{LOCAL_SQLITE_DB_PATH}")
    inspector = inspect(engine)
    if "raceprediction" not in inspector.get_table_names():
        pytest.skip(
            "Table raceprediction absente en DB locale - bootstrap non effectue."
        )
    columns = {col["name"] for col in inspector.get_columns("raceprediction")}
    assert "engine_version" in columns, (
        "La colonne `engine_version` est absente de la DB locale alors que la "
        "migration Alembic `v231_engine_version` aurait du la garantir."
    )


# -- 3. Adaptateur V2.2 : 3 clefs supportees ---------------------------------


def _make_observation(mean: float, std: float) -> dict:
    """Construit une observation minimale valide pour l'adaptateur."""
    return {
        "mean": mean,
        "std": std,
        "source_label": "test",
        "source_id": "1",
        "category": "submax",
        "weight": 1.0,
        "performed_at": None,
        "quality_flags": [],
    }


def test_v2_2_adapter_handles_p_ref_steady_wkg():
    """L'adaptateur V2.2 doit pouvoir consommer un dict d'observations
    publie par l'agregateur V2.3.1 (clef ``p_ref_steady_wkg``) et le
    convertir en ``flat_capacity_mps`` via la division par le cout plat
    Minetti.
    """
    observations = {
        "p_ref_steady_wkg": [_make_observation(mean=9.0, std=0.5)],
    }
    result = _flat_capacity_observations_compat(observations)
    assert len(result) == 1, (
        f"Attendu 1 observation convertie, obtenu {len(result)}"
    )
    expected_mps = 9.0 / MINETTI_FLAT_COST_J_PER_KG_M  # ~2.5 m/s
    assert abs(result[0]["mean"] - expected_mps) < 0.001, (
        f"Conversion W/kg -> m/s incorrecte : attendu {expected_mps:.4f}, "
        f"obtenu {result[0]['mean']:.4f}"
    )
    # La conversion doit poser le tag de quality flag pour traceability.
    assert "v2_3_aggregator_converted" in result[0]["quality_flags"], (
        "Le flag `v2_3_aggregator_converted` doit etre ajoute pour tracer "
        "la conversion W/kg -> m/s."
    )


def test_v2_2_adapter_handles_p_run_wkg_legacy():
    """L'adaptateur V2.2 doit pouvoir consommer la clef legacy V2.3
    ``p_run_wkg`` (avant la separation R1 V2.3.1).
    """
    observations = {
        "p_run_wkg": [_make_observation(mean=7.2, std=0.4)],
    }
    result = _flat_capacity_observations_compat(observations)
    assert len(result) == 1
    expected_mps = 7.2 / MINETTI_FLAT_COST_J_PER_KG_M  # ~2.0 m/s
    assert abs(result[0]["mean"] - expected_mps) < 0.001
    assert "v2_3_aggregator_converted" in result[0]["quality_flags"]


def test_v2_2_adapter_handles_flat_capacity_mps_native():
    """L'adaptateur V2.2 doit retourner directement les observations
    publiees sous la clef historique V2.2 ``flat_capacity_mps`` sans
    conversion (le contrat natif est deja en m/s).
    """
    observations = {
        "flat_capacity_mps": [_make_observation(mean=2.5, std=0.15)],
    }
    result = _flat_capacity_observations_compat(observations)
    assert len(result) == 1
    assert result[0]["mean"] == 2.5
    # Aucune conversion appliquee, donc pas de flag de conversion.
    assert "v2_3_aggregator_converted" not in result[0]["quality_flags"]
