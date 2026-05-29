"""
Tests du fix `_utc_naive` du router V2.2 (V2.3.1 - R6 partiel, livrable 3).

Avant le fix : la fonction utilisait ``value.astimezone(tz=None)`` qui convertit
vers le fuseau LOCAL du serveur. Sur un serveur europe/Paris, un datetime UTC
etait alors converti vers CEST/CET et range comme "naif local", ce qui
faussait toutes les comparaisons avec ``datetime.utcnow()``.

Apres le fix : la fonction convertit explicitement vers UTC via
``astimezone(timezone.utc)`` puis retire la tzinfo. Le datetime naif retourne
represente bien l'instant UTC, quelle que soit la timezone du serveur.

Cf. `docs/RACE_PREDICTOR_V2_3_FIX_PLAN.md` section R6.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.api.routers.prediction_v2_2_router import _utc_naive


def test_utc_naive_paris_summer_time_converts_to_utc() -> None:
    """
    Datetime aware en CEST (Europe/Paris ete, UTC+2) doit etre convertit en
    naive UTC : 07:00 Paris = 05:00 UTC.
    """
    aware = datetime(2026, 3, 29, 7, 0, tzinfo=ZoneInfo("Europe/Paris"))
    result = _utc_naive(aware)
    assert result == datetime(2026, 3, 29, 5, 0), (
        f"Conversion Paris -> UTC incorrecte : attendu 05:00 UTC, recu {result}"
    )
    assert result.tzinfo is None, "Le resultat doit etre naif (tzinfo=None)."


def test_utc_naive_paris_winter_time_converts_to_utc() -> None:
    """
    Datetime aware en CET (Europe/Paris hiver, UTC+1) doit etre converti :
    07:00 Paris hiver = 06:00 UTC.
    """
    aware = datetime(2026, 1, 15, 7, 0, tzinfo=ZoneInfo("Europe/Paris"))
    result = _utc_naive(aware)
    assert result == datetime(2026, 1, 15, 6, 0), (
        f"Conversion Paris hiver -> UTC incorrecte : attendu 06:00 UTC, recu {result}"
    )
    assert result.tzinfo is None


def test_utc_naive_utc_aware_returns_same_clock_value() -> None:
    """
    Datetime deja en UTC (tzinfo=timezone.utc) doit etre retourne avec
    exactement les memes valeurs d'horloge, juste prive de la tzinfo.
    """
    aware_utc = datetime(2026, 3, 29, 7, 0, tzinfo=timezone.utc)
    result = _utc_naive(aware_utc)
    assert result == datetime(2026, 3, 29, 7, 0)
    assert result.tzinfo is None


def test_utc_naive_naive_returns_as_is() -> None:
    """
    Convention API : un datetime naif est suppose deja UTC. La fonction le
    retourne tel quel sans conversion ni modification de la tzinfo.
    """
    naive = datetime(2026, 3, 29, 7, 0)
    result = _utc_naive(naive)
    assert result == naive
    assert result.tzinfo is None


def test_utc_naive_far_east_timezone_converts_correctly() -> None:
    """
    Datetime aware en Asia/Tokyo (UTC+9) : 09:00 Tokyo = 00:00 UTC le meme jour.
    """
    aware = datetime(2026, 3, 29, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = _utc_naive(aware)
    assert result == datetime(2026, 3, 29, 0, 0)
    assert result.tzinfo is None


def test_utc_naive_negative_offset_converts_correctly() -> None:
    """
    Datetime aware en America/New_York (UTC-5 hiver / UTC-4 ete) :
    20:00 NY le 15 janvier (EST) = 01:00 UTC le 16 janvier.
    """
    aware = datetime(2026, 1, 15, 20, 0, tzinfo=ZoneInfo("America/New_York"))
    result = _utc_naive(aware)
    assert result == datetime(2026, 1, 16, 1, 0)
    assert result.tzinfo is None


def test_utc_naive_always_returns_naive() -> None:
    """Invariant : peu importe l'entree, la sortie est toujours naive."""
    cases = [
        datetime(2026, 3, 29, 7, 0),
        datetime(2026, 3, 29, 7, 0, tzinfo=timezone.utc),
        datetime(2026, 3, 29, 7, 0, tzinfo=ZoneInfo("Europe/Paris")),
        datetime(2026, 6, 15, 12, 30, tzinfo=ZoneInfo("America/Los_Angeles")),
    ]
    for value in cases:
        result = _utc_naive(value)
        assert result.tzinfo is None, (
            f"_utc_naive({value!r}) renvoie un datetime aware : {result!r}"
        )
