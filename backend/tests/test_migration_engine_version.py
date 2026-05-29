"""
Tests de la migration Alembic V2.3.1 `v231_engine_version`.

Verifie :
- l'upgrade ajoute la colonne `engine_version` avec le bon type et default ;
- l'index `ix_raceprediction_engine_version` est present ;
- l'insertion sans specifier `engine_version` applique le default
  `v1_random_forest` (assure que les anciennes lignes restent compatibles) ;
- le downgrade reversible ;
- l'idempotence : appliquer la migration deux fois ne casse rien.

Approche : on ne replay PAS toute la chaine Alembic (certaines migrations
historiques utilisent `op.create_unique_constraint` sans `batch_alter_table`,
ce qui est incompatible avec une DB SQLite vide). On cree directement la
structure minimale via SQLModel (tables `user` + `raceprediction` AVANT ajout
de `engine_version`), on stamp Alembic au revision PRECEDENT
(`p0q1r2s3t4u5`), puis on applique notre migration cible.

Cette approche reflete bien le cas reel d'execution : la DB de prod sera
deja synchronisee jusqu'a `p0q1r2s3t4u5` quand notre migration sera deployee.

Reference : `docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md` - R6 partiel, livrable 2.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect


# Racine du backend.
BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Identifiants de la migration sous test.
TARGET_REVISION = "v231_engine_version"
PREVIOUS_REVISION = "p0q1r2s3t4u5"


@pytest.fixture()
def temp_sqlite_db() -> str:
    """Cree une DB SQLite vide dans un fichier temporaire et la nettoie ensuite."""
    fd, path = tempfile.mkstemp(suffix="_migration_test.db", prefix="stridedelta_")
    os.close(fd)
    try:
        yield path
    finally:
        if os.path.exists(path):
            os.unlink(path)


def _bootstrap_minimal_schema(db_path: str) -> None:
    """
    Cree une DB SQLite minimale pour tester la migration :
    - tables `user` et `raceprediction` (sans la colonne `engine_version`) ;
    - table `alembic_version` stampee au revision PRECEDENT.

    On ne charge PAS les modeles SQLModel pour eviter d'embarquer la
    declaration `engine_version` de l'entite. On cree donc les tables
    manuellement en DDL pur (SQL standard, fonctionne SQLite/Postgres).
    """
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        # User minimaliste (FK target).
        conn.execute(
            sa.text(
                "CREATE TABLE user ("
                " id CHAR(32) PRIMARY KEY,"
                " email VARCHAR(255) NOT NULL UNIQUE,"
                " hashed_password VARCHAR(255) NOT NULL,"
                " full_name VARCHAR(255),"
                " is_active BOOLEAN NOT NULL DEFAULT 1,"
                " created_at DATETIME NOT NULL,"
                " updated_at DATETIME NOT NULL"
                ")"
            )
        )
        # RacePrediction SANS engine_version (etat avant migration cible).
        conn.execute(
            sa.text(
                "CREATE TABLE raceprediction ("
                " id CHAR(32) PRIMARY KEY,"
                " user_id CHAR(32) NOT NULL,"
                " name VARCHAR NOT NULL,"
                " filename VARCHAR,"
                " analysis_mode VARCHAR NOT NULL DEFAULT 'trail',"
                " ravito_mode VARCHAR NOT NULL DEFAULT 'auto',"
                " history_start_date DATETIME,"
                " total_distance_km FLOAT,"
                " total_elevation_gain_m FLOAT,"
                " moving_time_min FLOAT,"
                " total_pause_min FLOAT,"
                " total_time_min FLOAT,"
                " avg_pace FLOAT,"
                " prediction_data JSON,"
                " created_at DATETIME NOT NULL,"
                " updated_at DATETIME NOT NULL,"
                " FOREIGN KEY(user_id) REFERENCES user(id)"
                ")"
            )
        )
        # Quelques index analogues a ceux du modele d'origine.
        conn.execute(sa.text(
            "CREATE INDEX ix_raceprediction_user_id ON raceprediction(user_id)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX ix_raceprediction_name ON raceprediction(name)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX ix_raceprediction_analysis_mode "
            "ON raceprediction(analysis_mode)"
        ))
        # Table de versioning Alembic, stampee au PRECEDENT.
        conn.execute(sa.text(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
        ))
        conn.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
            {"rev": PREVIOUS_REVISION},
        )


def _alembic_config(db_path: str):
    """Cree une config Alembic isolee pointant sur la DB temporaire.

    On ne reutilise PAS `env.py` (qui depend de `app.core.database.engine`
    fixe au load du module). A la place, on configure le contexte Alembic
    directement avec notre connection isolee, ce qui permet de tester
    plusieurs DBs differentes dans une meme session pytest.
    """
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _run_migration(
    db_path: str, action: str = "upgrade", revision: str = TARGET_REVISION
) -> None:
    """
    Applique une migration Alembic sur la DB temporaire en passant par
    l'API programmatique (`MigrationContext` + `Operations.context`) au lieu
    de `command.upgrade`.

    Cela court-circuite `env.py` (qui utilise un engine SQLModel partage
    incompatible avec des DBs temporaires multiples par session pytest).
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from alembic.operations import Operations

    engine = sa.create_engine(f"sqlite:///{db_path}")
    script = ScriptDirectory(str(BACKEND_ROOT / "alembic"))

    with engine.begin() as conn:
        context = MigrationContext.configure(connection=conn)
        rev = script.get_revision(revision)
        module = rev.module

        # `Operations.context(migration_context)` est la facade publique
        # d'Alembic pour activer le proxy global `op.*` utilise dans les
        # migrations. Cette API est documentee depuis Alembic 1.x.
        with Operations.context(context):
            if action == "upgrade":
                module.upgrade()
            elif action == "downgrade":
                module.downgrade()
            else:
                raise ValueError(f"Action inconnue: {action!r}")

        # Mise a jour manuelle de la table alembic_version (l'API
        # programmatique ne touche pas a la version par defaut).
        if action == "upgrade":
            conn.execute(
                sa.text("UPDATE alembic_version SET version_num = :rev"),
                {"rev": revision},
            )
        else:
            conn.execute(
                sa.text("UPDATE alembic_version SET version_num = :rev"),
                {"rev": rev.down_revision},
            )


def _connect(path: str) -> sa.engine.Engine:
    return sa.create_engine(f"sqlite:///{path}")


def test_upgrade_creates_engine_version_column(temp_sqlite_db: str) -> None:
    """Apres upgrade, la table raceprediction contient engine_version."""
    _bootstrap_minimal_schema(temp_sqlite_db)
    _run_migration(temp_sqlite_db, action="upgrade")

    engine = _connect(temp_sqlite_db)
    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("raceprediction")}

    assert "engine_version" in columns, (
        "Colonne engine_version absente apres upgrade."
    )
    col = columns["engine_version"]
    type_str = str(col["type"]).upper()
    assert "VARCHAR" in type_str or "STRING" in type_str, (
        f"Type inattendu pour engine_version : {col['type']}"
    )
    assert col["nullable"] is False, "engine_version devrait etre NOT NULL."


def test_upgrade_creates_index(temp_sqlite_db: str) -> None:
    """Apres upgrade, l'index ix_raceprediction_engine_version est present."""
    _bootstrap_minimal_schema(temp_sqlite_db)
    _run_migration(temp_sqlite_db, action="upgrade")

    engine = _connect(temp_sqlite_db)
    inspector = inspect(engine)
    indexes = {idx["name"]: idx for idx in inspector.get_indexes("raceprediction")}

    assert "ix_raceprediction_engine_version" in indexes
    assert indexes["ix_raceprediction_engine_version"]["column_names"] == [
        "engine_version"
    ]


def test_default_applied_when_value_omitted(temp_sqlite_db: str) -> None:
    """Inserer une ligne sans engine_version doit appliquer le default."""
    _bootstrap_minimal_schema(temp_sqlite_db)
    _run_migration(temp_sqlite_db, action="upgrade")

    engine = _connect(temp_sqlite_db)
    user_id = uuid4().hex
    prediction_id = uuid4().hex

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO user (id, email, hashed_password, full_name, "
                "is_active, created_at, updated_at) "
                "VALUES (:id, :email, :hp, :name, 1, "
                "  datetime('now'), datetime('now'))"
            ),
            {
                "id": user_id,
                "email": f"migrate_test_{user_id[:8]}@example.com",
                "hp": "fakehash",
                "name": "Migration Test",
            },
        )
        conn.execute(
            sa.text(
                "INSERT INTO raceprediction "
                "(id, user_id, name, analysis_mode, ravito_mode, "
                " prediction_data, created_at, updated_at) "
                "VALUES (:id, :user_id, :name, :am, :rm, '{}', "
                "  datetime('now'), datetime('now'))"
            ),
            {
                "id": prediction_id,
                "user_id": user_id,
                "name": "Test prediction",
                "am": "trail",
                "rm": "auto",
            },
        )

    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                "SELECT engine_version FROM raceprediction WHERE id = :id"
            ),
            {"id": prediction_id},
        ).fetchone()

    assert row is not None, "Ligne inseree introuvable."
    assert row[0] == "v1_random_forest", (
        f"Default engine_version non applique : valeur reelle = {row[0]!r}"
    )


def test_downgrade_removes_column(temp_sqlite_db: str) -> None:
    """Apres downgrade -1, la colonne engine_version disparait (SQLite batch op)."""
    _bootstrap_minimal_schema(temp_sqlite_db)
    _run_migration(temp_sqlite_db, action="upgrade")
    _run_migration(temp_sqlite_db, action="downgrade")

    engine = _connect(temp_sqlite_db)
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("raceprediction")}

    assert "engine_version" not in columns, (
        "engine_version est encore presente apres downgrade -1."
    )
    indexes = {idx["name"] for idx in inspector.get_indexes("raceprediction")}
    assert "ix_raceprediction_engine_version" not in indexes


def test_upgrade_is_idempotent_when_column_already_exists(
    temp_sqlite_db: str,
) -> None:
    """
    Replay scenario : le DDL runtime a deja cree la colonne avant Alembic.

    On ajoute manuellement la colonne avant d'appliquer la migration. Celle-ci
    doit etre un no-op (pas d'erreur "duplicate column"). Reflete exactement
    le cas reel ou la DB de prod a deja la colonne via
    `_ensure_race_prediction_table()` dans prediction_router.py.
    """
    _bootstrap_minimal_schema(temp_sqlite_db)

    # Simule l'effet du DDL runtime.
    engine = _connect(temp_sqlite_db)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "ALTER TABLE raceprediction ADD COLUMN engine_version VARCHAR "
                "DEFAULT 'v1_random_forest'"
            )
        )
        conn.execute(
            sa.text(
                "CREATE INDEX ix_raceprediction_engine_version "
                "ON raceprediction (engine_version)"
            )
        )

    # Appliquer la migration : doit reussir sans erreur.
    _run_migration(temp_sqlite_db, action="upgrade")

    # Verifier l'etat final.
    inspector = inspect(_connect(temp_sqlite_db))
    columns = {col["name"] for col in inspector.get_columns("raceprediction")}
    assert "engine_version" in columns
    indexes = {idx["name"] for idx in inspector.get_indexes("raceprediction")}
    assert "ix_raceprediction_engine_version" in indexes

    with _connect(temp_sqlite_db).begin() as conn:
        version_row = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).fetchone()
    assert version_row is not None
    assert version_row[0] == TARGET_REVISION
