"""
Tests du router Race Predictor V2.2 (Vague 2) :
  - profil athletique : GET / PUT / PATCH compat (upsert + validation) ;
  - tests de reference : GET / POST / PATCH / DELETE (soft-delete).

L'endpoint `POST /prediction/v2.2/gpx` est Vague 3 et n'est pas couvert ici.

Pattern de test : base SQLite isolee par fichier, dependency override
`get_session` sur l'app FastAPI globale, signup pour creer un user et
recuperer un JWT. Aucun mock d'auth : on utilise le vrai pipeline JWT
afin de detecter toute regression du contrat `Authorization: Bearer ...`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.api.routers._shared import limiter
from app.core.database import get_session
from app.main import app


SQLMODEL_DATABASE_URL = "sqlite:///./test_prediction_v2_2.db"
engine = create_engine(
    SQLMODEL_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


def _get_test_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = _get_test_session
# Desactive le rate limiter pour eviter les 429 sur /auth/signup (3/hour).
# Les tests creent plusieurs users a la suite ; le limiter n'est pas l'objet
# du test ici.
limiter.enabled = False


@pytest.fixture(scope="function")
def client():
    SQLModel.metadata.create_all(engine)
    yield TestClient(app)
    SQLModel.metadata.drop_all(engine)


def _signup(client: TestClient, *, email: str = "v22@example.com") -> str:
    """Cree un user via /auth/signup et retourne son access_token JWT."""
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "strongpassword123",
            "full_name": "V22 Tester",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /user/me/athletic-profile
# ---------------------------------------------------------------------------


def test_get_profile_without_auth_returns_401(client: TestClient) -> None:
    """Sans token Bearer ni cookie, l'endpoint retourne 401 (cf. _shared.security)."""
    response = client.get("/api/v1/user/me/athletic-profile")
    assert response.status_code == 401


def test_get_profile_no_profile_returns_null(client: TestClient) -> None:
    """Un profil non renseigne est un etat normal, pas une erreur reseau."""
    token = _signup(client)
    response = client.get(
        "/api/v1/user/me/athletic-profile",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json() is None


# ---------------------------------------------------------------------------
# PUT /user/me/athletic-profile (upsert)
# ---------------------------------------------------------------------------


def test_put_profile_creates_when_missing(client: TestClient) -> None:
    token = _signup(client)
    payload = {
        "sex": "male",
        "birth_date": "1992-06-15",
        "height_cm": 180.0,
        "weight_kg": 72.5,
        "activity_level": "active",
        "experience_level": "regular",
        "practice_dominant": "trail",
        "weekly_volume_band": "40_60km",
    }
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sex"] == "male"
    assert data["height_cm"] == pytest.approx(180.0)
    assert data["practice_dominant"] == "trail"
    assert data["weekly_volume_band"] == "40_60km"
    assert data["birth_date"] == "1992-06-15"
    assert "created_at" in data and "updated_at" in data

    # Verifions que GET le retrouve maintenant
    fetched = client.get(
        "/api/v1/user/me/athletic-profile",
        headers=_auth_headers(token),
    )
    assert fetched.status_code == 200
    assert fetched.json()["sex"] == "male"


def test_put_profile_updates_when_exists(client: TestClient) -> None:
    token = _signup(client)
    # Premiere creation
    client.put(
        "/api/v1/user/me/athletic-profile",
        json={"sex": "male", "height_cm": 180.0, "weight_kg": 72.5},
        headers=_auth_headers(token),
    )
    # Mise a jour partielle : seul weight_kg change
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json={"weight_kg": 70.0},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["weight_kg"] == pytest.approx(70.0)
    # Les autres champs sont preserves grace au merge (exclude_unset=True)
    assert data["sex"] == "male"
    assert data["height_cm"] == pytest.approx(180.0)


def test_patch_profile_remains_accepted_for_loaded_legacy_clients(client: TestClient) -> None:
    token = _signup(client)
    response = client.patch(
        "/api/v1/user/me/athletic-profile",
        json={"sex": "male", "height_cm": 180.0},
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json()["sex"] == "male"


def test_put_profile_invalid_height_returns_400(client: TestClient) -> None:
    token = _signup(client)
    # Trop petit
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json={"height_cm": 50.0},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400
    assert "height_cm" in response.json()["detail"]
    # Trop grand
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json={"height_cm": 300.0},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


def test_put_profile_invalid_weight_returns_400(client: TestClient) -> None:
    token = _signup(client)
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json={"weight_kg": 10.0},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400
    assert "weight_kg" in response.json()["detail"]


def test_put_profile_future_birth_date_returns_400(client: TestClient) -> None:
    token = _signup(client)
    future = (date.today() + timedelta(days=1)).isoformat()
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json={"birth_date": future},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400
    assert "birth_date" in response.json()["detail"]


def test_put_profile_too_old_birth_date_returns_400(client: TestClient) -> None:
    token = _signup(client)
    # > 100 ans
    too_old = date(date.today().year - 150, 1, 1).isoformat()
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json={"birth_date": too_old},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


def test_put_profile_invalid_enum_returns_422(client: TestClient) -> None:
    """Pydantic rejette une valeur d'enum invalide en 422 (validation native)."""
    token = _signup(client)
    response = client.put(
        "/api/v1/user/me/athletic-profile",
        json={"sex": "unknown"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /prediction/reference-tests
# ---------------------------------------------------------------------------


def test_get_reference_tests_empty_list_for_new_user(client: TestClient) -> None:
    token = _signup(client)
    response = client.get(
        "/api/v1/prediction/reference-tests",
        headers=_auth_headers(token),
    )
    assert response.status_code == 200
    assert response.json() == []


def test_get_reference_tests_without_auth_returns_401(client: TestClient) -> None:
    response = client.get("/api/v1/prediction/reference-tests")
    assert response.status_code == 401


def test_get_reference_tests_filter_by_type_works(client: TestClient) -> None:
    token = _signup(client)
    headers = _auth_headers(token)
    base = (datetime.utcnow() - timedelta(days=10)).isoformat()
    # Cree deux tests de types differents
    client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": base,
            "duration_seconds": 1100,
            "distance_m": 5000.0,
        },
        headers=headers,
    )
    client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_10k",
            "performed_at": base,
            "duration_seconds": 2400,
            "distance_m": 10000.0,
        },
        headers=headers,
    )

    response = client.get(
        "/api/v1/prediction/reference-tests?test_type=road_10k",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["test_type"] == "road_10k"


def test_get_reference_tests_excludes_invalidated_by_default(client: TestClient) -> None:
    token = _signup(client)
    headers = _auth_headers(token)
    base = (datetime.utcnow() - timedelta(days=5)).isoformat()
    create = client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": base,
            "duration_seconds": 1100,
            "distance_m": 5000.0,
        },
        headers=headers,
    )
    test_id = create.json()["id"]

    # Soft-delete via DELETE
    delete = client.delete(
        f"/api/v1/prediction/reference-tests/{test_id}",
        headers=headers,
    )
    assert delete.status_code == 204

    # Par defaut, le test invalide n'apparait plus
    response = client.get(
        "/api/v1/prediction/reference-tests",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json() == []

    # Avec include_invalidated, on le voit
    response = client.get(
        "/api/v1/prediction/reference-tests?include_invalidated=true",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["quality_status"] == "invalidated"


def test_get_reference_tests_sorted_by_performed_at_desc(client: TestClient) -> None:
    token = _signup(client)
    headers = _auth_headers(token)
    base = datetime.utcnow() - timedelta(days=30)
    # Cree dans le desordre
    older = (base - timedelta(days=10)).isoformat()
    newer = (base + timedelta(days=10)).isoformat()
    client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": older,
            "duration_seconds": 1100,
        },
        headers=headers,
    )
    client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_10k",
            "performed_at": newer,
            "duration_seconds": 2400,
        },
        headers=headers,
    )

    response = client.get(
        "/api/v1/prediction/reference-tests",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Le test le plus recent est en tete
    assert data[0]["test_type"] == "road_10k"
    assert data[1]["test_type"] == "road_5k"


# ---------------------------------------------------------------------------
# POST /prediction/reference-tests
# ---------------------------------------------------------------------------


def test_post_reference_test_creates_valid_road_10k(client: TestClient) -> None:
    token = _signup(client)
    payload = {
        "test_type": "road_10k",
        "performed_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
        "duration_seconds": 2400,
        "distance_m": 10000.0,
        "elevation_gain_m": 25.0,
        "temperature_c": 12.0,
        "surface": "asphalt",
        "conditions_notes": "Parcours mesure, sans vent.",
    }
    response = client.post(
        "/api/v1/prediction/reference-tests",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["test_type"] == "road_10k"
    assert data["duration_seconds"] == 2400
    assert data["surface"] == "asphalt"
    assert data["quality_status"] == "valid"
    assert data["warnings"] == []  # 10 000 m exact -> pas de warning


def test_post_reference_test_warns_when_distance_off(client: TestClient) -> None:
    """Un 5k qui mesure 6km doit creer le test mais retourner un warning."""
    token = _signup(client)
    payload = {
        "test_type": "road_5k",
        "performed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        "duration_seconds": 1500,
        "distance_m": 6000.0,  # 20% au-dessus
    }
    response = client.post(
        "/api/v1/prediction/reference-tests",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 201
    data = response.json()
    assert len(data["warnings"]) == 1
    assert "distance_m" in data["warnings"][0]


def test_post_reference_test_invalid_duration_returns_400(client: TestClient) -> None:
    token = _signup(client)
    payload = {
        "test_type": "road_5k",
        "performed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        "duration_seconds": 0,
    }
    response = client.post(
        "/api/v1/prediction/reference-tests",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 400
    assert "duration_seconds" in response.json()["detail"]


def test_post_reference_test_negative_duration_returns_400(client: TestClient) -> None:
    token = _signup(client)
    payload = {
        "test_type": "road_5k",
        "performed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        "duration_seconds": -10,
    }
    response = client.post(
        "/api/v1/prediction/reference-tests",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


def test_post_reference_test_future_performed_at_returns_400(client: TestClient) -> None:
    token = _signup(client)
    payload = {
        "test_type": "road_5k",
        "performed_at": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        "duration_seconds": 1100,
    }
    response = client.post(
        "/api/v1/prediction/reference-tests",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 400
    assert "performed_at" in response.json()["detail"]


def test_post_reference_test_invalid_type_returns_422(client: TestClient) -> None:
    token = _signup(client)
    payload = {
        "test_type": "marathon",  # pas dans l'enum
        "performed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        "duration_seconds": 9000,
    }
    response = client.post(
        "/api/v1/prediction/reference-tests",
        json=payload,
        headers=_auth_headers(token),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /prediction/reference-tests/{id}
# ---------------------------------------------------------------------------


def test_patch_reference_test_owner_can_invalidate(client: TestClient) -> None:
    token = _signup(client)
    headers = _auth_headers(token)
    create = client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_10k",
            "performed_at": (datetime.utcnow() - timedelta(days=3)).isoformat(),
            "duration_seconds": 2400,
            "distance_m": 10000.0,
        },
        headers=headers,
    )
    test_id = create.json()["id"]

    response = client.patch(
        f"/api/v1/prediction/reference-tests/{test_id}",
        json={"quality_status": "questionable", "conditions_notes": "Vent fort"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["quality_status"] == "questionable"
    assert data["conditions_notes"] == "Vent fort"


def test_patch_reference_test_not_owner_returns_404(client: TestClient) -> None:
    """User B ne doit pas pouvoir modifier un test appartenant a User A : 404 (pas 403)."""
    token_a = _signup(client, email="usera@example.com")
    create = client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
            "duration_seconds": 1200,
        },
        headers=_auth_headers(token_a),
    )
    test_id = create.json()["id"]

    # User B essaie de patch
    token_b = _signup(client, email="userb@example.com")
    response = client.patch(
        f"/api/v1/prediction/reference-tests/{test_id}",
        json={"quality_status": "invalidated"},
        headers=_auth_headers(token_b),
    )
    assert response.status_code == 404


def test_patch_reference_test_unknown_id_returns_404(client: TestClient) -> None:
    token = _signup(client)
    response = client.patch(
        f"/api/v1/prediction/reference-tests/{uuid4()}",
        json={"quality_status": "invalidated"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


def test_patch_reference_test_negative_duration_returns_400(client: TestClient) -> None:
    token = _signup(client)
    headers = _auth_headers(token)
    create = client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            "duration_seconds": 1100,
        },
        headers=headers,
    )
    test_id = create.json()["id"]

    response = client.patch(
        f"/api/v1/prediction/reference-tests/{test_id}",
        json={"duration_seconds": 0},
        headers=headers,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# DELETE /prediction/reference-tests/{id}
# ---------------------------------------------------------------------------


def test_delete_reference_test_marks_invalidated_returns_204(client: TestClient) -> None:
    token = _signup(client)
    headers = _auth_headers(token)
    create = client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            "duration_seconds": 1100,
        },
        headers=headers,
    )
    test_id = create.json()["id"]

    response = client.delete(
        f"/api/v1/prediction/reference-tests/{test_id}",
        headers=headers,
    )
    assert response.status_code == 204
    # Le body doit etre vide pour un 204
    assert response.content in (b"", b"null")

    # Le test existe toujours en base (soft-delete) et est invalide
    listing = client.get(
        "/api/v1/prediction/reference-tests?include_invalidated=true",
        headers=headers,
    )
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["quality_status"] == "invalidated"
    assert items[0]["id"] == test_id


def test_delete_reference_test_unknown_id_returns_404(client: TestClient) -> None:
    token = _signup(client)
    response = client.delete(
        f"/api/v1/prediction/reference-tests/{uuid4()}",
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


def test_delete_reference_test_not_owner_returns_404(client: TestClient) -> None:
    token_a = _signup(client, email="ownera@example.com")
    create = client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
            "duration_seconds": 1100,
        },
        headers=_auth_headers(token_a),
    )
    test_id = create.json()["id"]

    token_b = _signup(client, email="strangerb@example.com")
    response = client.delete(
        f"/api/v1/prediction/reference-tests/{test_id}",
        headers=_auth_headers(token_b),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


def test_get_reference_tests_only_returns_own_tests(client: TestClient) -> None:
    token_a = _signup(client, email="iso-a@example.com")
    token_b = _signup(client, email="iso-b@example.com")

    client.post(
        "/api/v1/prediction/reference-tests",
        json={
            "test_type": "road_5k",
            "performed_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            "duration_seconds": 1100,
        },
        headers=_auth_headers(token_a),
    )

    response = client.get(
        "/api/v1/prediction/reference-tests",
        headers=_auth_headers(token_b),
    )
    assert response.status_code == 200
    assert response.json() == []


def test_get_athletic_profile_only_returns_own(client: TestClient) -> None:
    token_a = _signup(client, email="profile-a@example.com")
    token_b = _signup(client, email="profile-b@example.com")

    client.put(
        "/api/v1/user/me/athletic-profile",
        json={"sex": "female", "height_cm": 165.0},
        headers=_auth_headers(token_a),
    )

    # User B n'a toujours pas de profil : le contrat retourne null.
    response = client.get(
        "/api/v1/user/me/athletic-profile",
        headers=_auth_headers(token_b),
    )
    assert response.status_code == 200
    assert response.json() is None


# ---------------------------------------------------------------------------
# POST /prediction/v2.2/gpx  (Vague 3 - prediction Bayesienne)
# ---------------------------------------------------------------------------


# Compact GPX fixture: ~6 km flat-ish loop, no time stamps. Suffices to drive
# analyze_gpx + physics engine + Monte Carlo. Kept inline (rather than reading
# from disk) so the test stays self-contained and deterministic.
_GPX_BYTES = (
    b"<?xml version='1.0' encoding='UTF-8'?>\n"
    b"<gpx version='1.1' creator='test'>\n"
    b"<trk><name>test</name><trkseg>\n"
    + b"".join(
        f"<trkpt lat='46.6{i:03d}' lon='6.4{i:03d}'><ele>{500 + (i % 7) * 5}</ele></trkpt>\n".encode()
        for i in range(40)
    )
    + b"</trkseg></trk>\n</gpx>\n"
)


def test_v2_2_endpoint_returns_401_without_auth(client: TestClient) -> None:
    """Sans token Bearer ni cookie, l'endpoint retourne 401."""
    response = client.post(
        "/api/v1/prediction/v2.2/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={"effort_mode": "steady"},
    )
    assert response.status_code == 401


def test_v2_2_endpoint_returns_200_with_minimal_inputs(client: TestClient) -> None:
    """Avec un token valide et un GPX minimal, l'endpoint retourne 200 et la
    structure V2.2 attendue (engine_version, summary, athlete_model)."""
    token = _signup(client, email="v22-pred@example.com")
    response = client.post(
        "/api/v1/prediction/v2.2/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
            "ravito_mode": "auto",
        },
        # FIX 6b (V2.3.1) : V2.2 endpoint refuse l'usage interactif depuis
        # l'UI. Le header X-Source: benchmark autorise les tests/benchmarks.
        headers={**_auth_headers(token), "X-Source": "benchmark"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine_version"] == "v2_2_bayesian"
    # Core fields the V2 frontend already consumes.
    assert "summary" in body
    assert "uncertainty" in body
    assert "segments" in body and isinstance(body["segments"], list)
    assert body["segments"], "Segments list should be non-empty"
    assert "total_time_min" in body["summary"]
    # V2.2-specific blocks.
    assert "athlete_model" in body
    assert "event_intensity" in body
    assert "debug_trace" in body
    assert body["debug_trace"]["engine_version"] == "v2_2_bayesian"


def test_v2_2_endpoint_returns_athlete_model_in_response(client: TestClient) -> None:
    """Le bloc athlete_model doit etre present meme sans profil ni evidence."""
    token = _signup(client, email="v22-athlete@example.com")
    response = client.post(
        "/api/v1/prediction/v2.2/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "auto",
            "weather_mode": "manual",
            "temperature_c": "10.0",
        },
        # FIX 6b: bypass interactive block via X-Source: benchmark.
        headers={**_auth_headers(token), "X-Source": "benchmark"},
    )
    assert response.status_code == 200, response.text
    am = response.json()["athlete_model"]
    assert set(am.keys()) >= {
        "prior",
        "posterior",
        "evidence_summary",
        "recommended_next_evidence",
        "profile_present",
    }
    # profile_present is False without a profile, and the recommendation list
    # is non-empty (at least: complete_profile).
    assert am["profile_present"] is False
    actions = [r["action"] for r in am["recommended_next_evidence"]]
    assert "complete_profile" in actions


def test_v2_2_endpoint_handles_invalid_gpx_400(client: TestClient) -> None:
    """Un GPX vide ou sans trace exploitable doit retourner 400 (pas 500)."""
    token = _signup(client, email="v22-bad-gpx@example.com")
    response = client.post(
        "/api/v1/prediction/v2.2/gpx",
        files={"file": ("bad.gpx", b"not-a-gpx", "application/gpx+xml")},
        data={"effort_mode": "steady"},
        # FIX 6b: bypass interactive block via X-Source: benchmark.
        headers={**_auth_headers(token), "X-Source": "benchmark"},
    )
    assert response.status_code == 400, response.text
    assert "GPX" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /prediction/v2.3/gpx  (Race Predictor V2.3 - sans double comptage)
# ---------------------------------------------------------------------------


def test_v2_3_endpoint_returns_401_without_auth(client: TestClient) -> None:
    """Sans token Bearer ni cookie, l'endpoint V2.3 retourne 401."""
    response = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={"effort_mode": "steady"},
    )
    assert response.status_code == 401


def test_v2_3_endpoint_returns_200_with_minimal_inputs(client: TestClient) -> None:
    """Avec un token valide et un GPX minimal, l'endpoint V2.3 retourne 200
    et la structure attendue (engine_version, summary, athlete_model,
    physics_inputs)."""
    token = _signup(client, email="v23-pred@example.com")
    response = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
            "ravito_mode": "auto",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "summary" in body
    assert "uncertainty" in body
    assert "segments" in body and isinstance(body["segments"], list)
    assert body["segments"], "Segments list should be non-empty"
    assert "total_time_min" in body["summary"]
    assert "athlete_model" in body
    assert "physics_inputs" in body
    assert "debug_trace" in body


def test_v2_3_endpoint_returns_engine_version_v2_3(client: TestClient) -> None:
    """engine_version retourne par l'endpoint /v2.3/gpx doit etre
    `v2_3_1_bayesian` (R4 : le router surcharge la valeur emise par le service
    core). Les anciennes predictions stockees avec `v2_3_bayesian` restent
    lisibles mais toute nouvelle prediction est etiquettee V2.3.1."""
    token = _signup(client, email="v23-version@example.com")
    response = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine_version"] == "v2_3_1_bayesian"
    assert body["debug_trace"]["engine_version"] == "v2_3_1_bayesian"
    assert body["calibration"]["engine_version"] == "v2_3_1_bayesian"


def test_v2_3_endpoint_distinct_response_from_v2_2(client: TestClient) -> None:
    """V2.2 et V2.3 cohabitent : les deux endpoints repondent 200 mais avec
    des engine_version differents. V2.3 expose physics_inputs, V2.2 expose
    event_intensity."""
    token = _signup(client, email="v23-vs-v22@example.com")
    v22 = client.post(
        "/api/v1/prediction/v2.2/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
        },
        # FIX 6b: bypass interactive block via X-Source: benchmark.
        headers={**_auth_headers(token), "X-Source": "benchmark"},
    )
    v23 = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
        },
        headers=_auth_headers(token),
    )
    assert v22.status_code == 200, v22.text
    assert v23.status_code == 200, v23.text

    v22_body = v22.json()
    v23_body = v23.json()
    assert v22_body["engine_version"] == "v2_2_bayesian"
    # R4 : l'endpoint /v2.3/gpx etiquette desormais ses sorties en v2_3_1_bayesian.
    assert v23_body["engine_version"] == "v2_3_1_bayesian"

    # V2.2 exposes event_intensity (iterate_event_power); V2.3 must not.
    assert "event_intensity" in v22_body
    assert "physics_inputs" in v23_body
    assert "event_intensity" not in v23_body
    assert "physics_inputs" not in v22_body
    # V2.3 athlete_model uses the new "p_run_wkg" key in prior/posterior,
    # while V2.2 uses "flat_capacity_mps".
    assert "p_run_wkg" in v23_body["athlete_model"]["prior"]
    assert "p_run_wkg" in v23_body["athlete_model"]["posterior"]
    assert "flat_capacity_mps" in v22_body["athlete_model"]["prior"]


def test_v2_3_endpoint_handles_invalid_gpx_400(client: TestClient) -> None:
    """Un GPX vide ou sans trace exploitable doit retourner 400 (pas 500)."""
    token = _signup(client, email="v23-bad-gpx@example.com")
    response = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("bad.gpx", b"not-a-gpx", "application/gpx+xml")},
        data={"effort_mode": "steady"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400, response.text
    assert "GPX" in response.json()["detail"]


# ---------------------------------------------------------------------------
# R4 - Nouveaux tests V2.3.1 (warning target_heartrate, override engine_version)
# ---------------------------------------------------------------------------


def test_v2_3_endpoint_warns_when_target_heartrate_sent(client: TestClient) -> None:
    """R4 livrable 6 : si le client envoie ``target_heartrate``, le backend
    doit emettre un warning explicite dans ``warnings`` pour signaler que le
    champ est conserve dans le contrat API mais pas encore consomme par le
    moteur V2.3.1. L'UI V2.3 ne propose plus le champ."""
    token = _signup(client, email="v23-hr-warning@example.com")
    response = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
            "target_heartrate": "155",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    warnings = body.get("warnings") or []
    expected = "target_heartrate received but not yet consumed by V2.3.1 engine"
    assert any(expected in w for w in warnings), (
        f"target_heartrate warning manquant. warnings recus: {warnings}"
    )


def test_v2_3_endpoint_no_target_heartrate_warning_when_absent(client: TestClient) -> None:
    """Sans ``target_heartrate``, aucun warning V2.3.1 specifique ne doit
    etre emis (sanity check : on ne genere pas le warning par defaut)."""
    token = _signup(client, email="v23-no-hr@example.com")
    response = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    warnings = response.json().get("warnings") or []
    forbidden = "target_heartrate received but not yet consumed by V2.3.1 engine"
    assert not any(forbidden in w for w in warnings), (
        f"warning target_heartrate emis a tort. warnings recus: {warnings}"
    )


def test_v2_3_endpoint_saves_with_engine_version_v2_3_1_bayesian(client: TestClient) -> None:
    """R4 livrable 2 : toute nouvelle prediction etiquetee V2.3.1 doit etre
    sauvegardable via POST /prediction/saved avec
    ``engine_version = v2_3_1_bayesian`` dans la colonne dediee ET dans
    ``prediction_data.engine_version``.

    Reproduit le workflow utilisateur reel : appel /v2.3/gpx puis sauvegarde
    du resultat. Verifie qu'apres rechargement via /prediction/saved, l'engine
    version est bien etiquetee V2.3.1.
    """
    token = _signup(client, email="v23-save@example.com")
    # 1. Calcul de la prediction V2.3.1
    prediction_response = client.post(
        "/api/v1/prediction/v2.3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
        },
        headers=_auth_headers(token),
    )
    assert prediction_response.status_code == 200, prediction_response.text
    prediction_body = prediction_response.json()
    assert prediction_body["engine_version"] == "v2_3_1_bayesian"

    # 2. Sauvegarde (reproduit l'action du bouton Enregistrer cote frontend)
    save_response = client.post(
        "/api/v1/prediction/saved",
        json={
            "name": "Prediction V2.3.1 de test",
            "prediction": prediction_body,
            "history_start_date": "2025-01-01T00:00:00",
        },
        headers=_auth_headers(token),
    )
    assert save_response.status_code == 200, save_response.text
    saved_body = save_response.json()
    assert saved_body["engine_version"] == "v2_3_1_bayesian"
    assert saved_body["prediction_data"]["engine_version"] == "v2_3_1_bayesian"

    # 3. Liste et verifie l'apparition de la prediction sauvegardee
    list_response = client.get(
        "/api/v1/prediction/saved",
        headers=_auth_headers(token),
    )
    assert list_response.status_code == 200, list_response.text
    items = list_response.json().get("items", [])
    matching = [
        item
        for item in items
        if item.get("name") == "Prediction V2.3.1 de test"
    ]
    assert len(matching) == 1
    assert matching[0]["engine_version"] == "v2_3_1_bayesian"


# ---------------------------------------------------------------------------
# V2.3.1 FIX 1 - history_start_date transmis au service
# ---------------------------------------------------------------------------


def test_v2_3_endpoint_passes_history_start_date_to_service(
    client: TestClient, monkeypatch
) -> None:
    """FIX 1 (V2.3.1) : le router doit reellement transmettre
    ``history_start_date`` au service ``predict_v2_3``.

    Regression : avant le fix, le parametre etait parse mais jamais transmis
    a ``predict_v2_3``, donc deux requetes avec des windows differentes
    produisaient le meme resultat. Ce test monkey-patche le service pour
    capturer la valeur recue par chaque appel et asserter que les deux sont
    differentes.
    """
    token = _signup(client, email="v23-history-start-date@example.com")
    captured_calls: list = []

    def mock_predict_v2_3(session, user_id, gpx_text, **kwargs):
        captured_calls.append(kwargs.get("history_start_date"))
        return {
            "engine_version": "v2_3_1_bayesian",
            "warnings": [],
            "athlete_model": {
                "evidence_summary": {
                    "total_observations_count": len(captured_calls),
                },
            },
        }

    # Le namespace ``app.api.routers.prediction_v2_2_router`` (alias dans
    # ``app/api/routers/__init__.py``) pointe vers l'APIRouter ; pour patcher
    # le symbole importe dans le MODULE, on accede au module via sys.modules.
    import sys

    module = sys.modules["app.api.routers.prediction_v2_2_router"]
    monkeypatch.setattr(module, "predict_v2_3", mock_predict_v2_3)

    resp1 = client.post(
        "/api/v1/prediction/v2.3/gpx",
        headers=_auth_headers(token),
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "history_start_date": "2024-01-01T00:00:00",
            "race_datetime": "2026-04-01T07:00:00",
        },
    )
    assert resp1.status_code == 200, resp1.text

    resp2 = client.post(
        "/api/v1/prediction/v2.3/gpx",
        headers=_auth_headers(token),
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "history_start_date": "2022-01-01T00:00:00",
            "race_datetime": "2026-04-01T07:00:00",
        },
    )
    assert resp2.status_code == 200, resp2.text

    assert len(captured_calls) == 2
    assert captured_calls[0] is not None
    assert captured_calls[1] is not None
    assert captured_calls[0] != captured_calls[1], (
        "Le routeur doit transmettre des history_start_date differentes au "
        "service (FIX 1 V2.3.1)."
    )


# ---------------------------------------------------------------------------
# V2.3.1 FIX 3 - ENGINE_VERSION provient du service, pas d'override router
# ---------------------------------------------------------------------------


def test_engine_version_comes_from_service_not_router_override() -> None:
    """FIX 3 (V2.3.1) : la constante ENGINE_VERSION du service doit valoir
    ``v2_3_1_bayesian`` directement, et le router ne doit plus contenir le
    bloc d'override sale.
    """
    import pathlib

    from app.domain.services.race_predictor.v2_3_prediction_service import (
        ENGINE_VERSION,
    )

    assert ENGINE_VERSION == "v2_3_1_bayesian"

    router_src = pathlib.Path(
        "/Users/andrebertea/Projects/athletIQ/backend/app/api/routers/"
        "prediction_v2_2_router.py"
    ).read_text()
    assert 'result["engine_version"] = "v2_3_1_bayesian"' not in router_src, (
        "Le router ne doit plus contenir d'override sale de engine_version "
        "(FIX 3 V2.3.1)."
    )


# ---------------------------------------------------------------------------
# V2.3.1 FIX 6b - endpoint V2.2 bloque pour usage interactif
# ---------------------------------------------------------------------------


def test_v2_2_endpoint_blocks_interactive_use(client: TestClient) -> None:
    """FIX 6b (V2.3.1) : sans header ``X-Source: benchmark``, l'endpoint
    V2.2 retourne 410 Gone. V2.2 reste appelable depuis les scripts
    benchmark (header explicite) mais plus depuis l'UI utilisateur.
    """
    token = _signup(client, email="v22-blocked-interactive@example.com")
    response = client.post(
        "/api/v1/prediction/v2.2/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={"effort_mode": "steady"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 410, response.text
    detail = response.json()["detail"]
    assert "V2.2" in detail
    assert "deprecated" in detail.lower()


def test_v2_2_endpoint_allows_benchmark_with_header(client: TestClient) -> None:
    """FIX 6b (V2.3.1) : avec le header ``X-Source: benchmark``, l'endpoint
    V2.2 reste fonctionnel (200) mais marque ``X-Deprecated-Endpoint: true``.
    """
    token = _signup(client, email="v22-allow-benchmark@example.com")
    response = client.post(
        "/api/v1/prediction/v2.2/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
        },
        headers={**_auth_headers(token), "X-Source": "benchmark"},
    )
    assert response.status_code == 200, response.text
    # Le header de depreciation reste pour signaler au client benchmark
    # qu'il utilise une route deprecated.
    assert response.headers.get("X-Deprecated-Endpoint") == "true"


def test_v3_endpoint_returns_distinct_engine_and_hybrid_trace(client: TestClient) -> None:
    token = _signup(client, email="v3-endpoint@example.com")
    response = client.post(
        "/api/v1/prediction/v3/gpx",
        files={"file": ("test.gpx", _GPX_BYTES, "application/gpx+xml")},
        data={
            "effort_mode": "steady",
            "analysis_mode": "trail",
            "weather_mode": "manual",
            "temperature_c": "12.0",
        },
        headers=_auth_headers(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["engine_version"] == "v3_hybrid"
    assert body["hybrid_model"]["evidence_policy"] == "weighted_sparse"
    assert body["hybrid_model"]["residual_correction"]["applied"] is False
