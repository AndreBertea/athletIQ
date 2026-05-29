"""
Tests pour RedisQuotaManager — gestion des quotas API Strava via Redis.

Tous les tests utilisent un mock du client Redis (pas besoin de serveur réel).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import redis

from app.domain.services.redis_quota_manager import (
    DAILY_KEY,
    DAILY_LIMIT,
    PER_15MIN_LIMIT,
    SHORT_KEY,
    RedisQuotaManager,
    _seconds_until_midnight_utc,
)


@pytest.fixture
def mock_redis():
    """Client Redis mocké avec un store interne simple."""
    r = MagicMock(spec=redis.Redis)
    store = {}
    ttls = {}

    def _get(key):
        return store.get(key)

    def _set(key, value):
        store[key] = str(value)
        return True

    def _incr(key):
        val = int(store.get(key, 0)) + 1
        store[key] = str(val)
        return val

    def _ttl(key):
        if key not in store:
            return -2  # clé inexistante
        return ttls.get(key, -1)  # -1 = pas de TTL

    def _expire(key, seconds):
        ttls[key] = seconds
        return True

    def _delete(*keys):
        for k in keys:
            store.pop(k, None)
            ttls.pop(k, None)

    r.get = MagicMock(side_effect=_get)
    r.set = MagicMock(side_effect=_set)
    r.incr = MagicMock(side_effect=_incr)
    r.ttl = MagicMock(side_effect=_ttl)
    r.expire = MagicMock(side_effect=_expire)
    r.delete = MagicMock(side_effect=_delete)

    # Exposer le store interne pour les assertions
    r._store = store
    r._ttls = ttls
    return r


@pytest.fixture
def manager(mock_redis):
    return RedisQuotaManager(redis_client=mock_redis)


# ---------------------------------------------------------------
# _seconds_until_midnight_utc
# ---------------------------------------------------------------

class TestSecondsUntilMidnight:

    def test_returns_positive_value(self):
        result = _seconds_until_midnight_utc()
        assert result >= 1
        assert result <= 86400

    @patch("app.domain.services.redis_quota_manager.datetime")
    def test_returns_1_at_exact_midnight(self, mock_dt):
        """À minuit pile, doit retourner au minimum 1 (pas 0)."""
        fake_now = datetime(2026, 2, 7, 0, 0, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _seconds_until_midnight_utc()
        assert result >= 1

    @patch("app.domain.services.redis_quota_manager.datetime")
    def test_returns_correct_seconds_at_23h(self, mock_dt):
        """À 23:00:00 UTC → ~3600 secondes restantes."""
        fake_now = datetime(2026, 2, 7, 23, 0, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        result = _seconds_until_midnight_utc()
        assert result == 3600


# ---------------------------------------------------------------
# _safe_get / _safe_incr
# ---------------------------------------------------------------

class TestSafeGetAndIncr:

    def test_safe_get_returns_0_when_key_missing(self, manager, mock_redis):
        assert manager._safe_get(DAILY_KEY) == 0

    def test_safe_get_returns_value(self, manager, mock_redis):
        mock_redis._store[DAILY_KEY] = "42"
        mock_redis._ttls[DAILY_KEY] = 500  # TTL existant
        assert manager._safe_get(DAILY_KEY) == 42

    def test_safe_get_fixes_orphan_key(self, manager, mock_redis):
        """Clé sans TTL → _safe_get réapplique le TTL."""
        mock_redis._store[DAILY_KEY] = "10"
        # pas de TTL → ttl retourne -1
        manager._safe_get(DAILY_KEY)
        mock_redis.expire.assert_called()

    def test_safe_get_fixes_orphan_short_key(self, manager, mock_redis):
        """Clé 15min sans TTL → réapplication TTL 900s."""
        mock_redis._store[SHORT_KEY] = "5"
        manager._safe_get(SHORT_KEY)
        # Vérifier que expire a été appelé avec 900
        mock_redis.expire.assert_called_with(SHORT_KEY, 900)

    def test_safe_get_redis_down(self, manager, mock_redis):
        """Redis indisponible → retourne 0 sans crash."""
        mock_redis.get.side_effect = redis.RedisError("Connection refused")
        assert manager._safe_get(DAILY_KEY) == 0

    def test_safe_incr_first_call_sets_ttl(self, manager, mock_redis):
        """Premier INCR (val=1) → pose le TTL."""
        result = manager._safe_incr(SHORT_KEY, 900)
        assert result == 1
        mock_redis.expire.assert_called_with(SHORT_KEY, 900)

    def test_safe_incr_subsequent_no_extra_expire(self, manager, mock_redis):
        """INCR suivant avec TTL existant → pas d'expire supplémentaire."""
        # Premier appel
        manager._safe_incr(SHORT_KEY, 900)
        mock_redis.expire.reset_mock()
        # Deuxième appel — la clé a un TTL
        mock_redis._ttls[SHORT_KEY] = 850
        manager._safe_incr(SHORT_KEY, 900)
        # expire ne doit PAS être rappelé (clé a déjà un TTL)
        mock_redis.expire.assert_not_called()

    def test_safe_incr_fixes_orphan_key(self, manager, mock_redis):
        """INCR sur clé orpheline (sans TTL, val > 1) → réapplique le TTL."""
        # Simuler une clé existante sans TTL
        mock_redis._store[DAILY_KEY] = "5"
        # ttl retourne -1 (pas de TTL)
        manager._safe_incr(DAILY_KEY, 3600)
        # La val est 6 (pas 1), donc on entre dans le elif
        mock_redis.expire.assert_called_with(DAILY_KEY, 3600)

    def test_safe_incr_redis_down(self, manager, mock_redis):
        """Redis indisponible → retourne 0 sans crash."""
        mock_redis.incr.side_effect = redis.RedisError("Timeout")
        result = manager._safe_incr(DAILY_KEY, 3600)
        assert result == 0


# ---------------------------------------------------------------
# Propriétés daily_count / per_15min_count
# ---------------------------------------------------------------

class TestProperties:

    def test_daily_count_reads_from_redis(self, manager, mock_redis):
        mock_redis._store[DAILY_KEY] = "75"
        mock_redis._ttls[DAILY_KEY] = 100
        assert manager.daily_count == 75

    def test_daily_count_setter_preserves_ttl(self, manager, mock_redis):
        """Forcer le daily_count doit conserver le TTL existant."""
        mock_redis._store[DAILY_KEY] = "50"
        mock_redis._ttls[DAILY_KEY] = 1234
        manager.daily_count = 999
        assert mock_redis._store[DAILY_KEY] == "999"
        mock_redis.expire.assert_called_with(DAILY_KEY, 1234)

    def test_daily_count_setter_no_ttl_sets_midnight(self, manager, mock_redis):
        """Forcer daily_count sans TTL existant → TTL = secondes jusqu'à minuit."""
        manager.daily_count = 500
        assert mock_redis._store[DAILY_KEY] == "500"
        # expire appelé avec un TTL > 0
        _, kwargs = mock_redis.expire.call_args
        if not kwargs:
            args = mock_redis.expire.call_args[0]
            assert args[1] >= 1

    def test_daily_count_setter_redis_down(self, manager, mock_redis):
        """Redis down → setter silencieux."""
        mock_redis.get.side_effect = redis.RedisError("Down")
        mock_redis.set.side_effect = redis.RedisError("Down")
        # Ne doit pas lever d'exception
        manager.daily_count = 100

    def test_per_15min_count_reads_from_redis(self, manager, mock_redis):
        mock_redis._store[SHORT_KEY] = "30"
        mock_redis._ttls[SHORT_KEY] = 100
        assert manager.per_15min_count == 30


# ---------------------------------------------------------------
# check_and_wait_if_needed
# ---------------------------------------------------------------

class TestCheckAndWait:

    def test_returns_true_when_under_quota(self, manager, mock_redis):
        mock_redis._store[DAILY_KEY] = "10"
        mock_redis._ttls[DAILY_KEY] = 100
        mock_redis._store[SHORT_KEY] = "5"
        mock_redis._ttls[SHORT_KEY] = 100
        assert manager.check_and_wait_if_needed() is True

    def test_returns_false_when_daily_quota_reached(self, manager, mock_redis):
        mock_redis._store[DAILY_KEY] = str(DAILY_LIMIT)
        mock_redis._ttls[DAILY_KEY] = 100
        assert manager.check_and_wait_if_needed() is False

    def test_returns_false_when_daily_exceeded(self, manager, mock_redis):
        mock_redis._store[DAILY_KEY] = str(DAILY_LIMIT + 50)
        mock_redis._ttls[DAILY_KEY] = 100
        assert manager.check_and_wait_if_needed() is False

    def test_returns_false_when_15min_quota_reached(self, manager, mock_redis):
        """Quota 15min atteint -> differe l'enrichissement sans bloquer."""
        mock_redis._store[DAILY_KEY] = "10"
        mock_redis._ttls[DAILY_KEY] = 100
        mock_redis._store[SHORT_KEY] = str(PER_15MIN_LIMIT)
        mock_redis._ttls[SHORT_KEY] = 120
        result = manager.check_and_wait_if_needed()
        assert result is False

    def test_returns_false_when_15min_quota_ttl_is_expiring(self, manager, mock_redis):
        """Un quota signale comme plein reste non bloquant meme si son TTL expire."""
        mock_redis._store[DAILY_KEY] = "10"
        mock_redis._ttls[DAILY_KEY] = 100
        mock_redis._store[SHORT_KEY] = str(PER_15MIN_LIMIT)
        mock_redis._ttls[SHORT_KEY] = 0
        result = manager.check_and_wait_if_needed()
        assert result is False

    def test_returns_false_when_ttl_read_fails_after_full_quota(self, manager, mock_redis):
        """Une erreur de lecture du TTL ne doit pas autoriser ni bloquer l'appel."""
        mock_redis._store[DAILY_KEY] = "10"
        mock_redis._ttls[DAILY_KEY] = 100
        mock_redis._store[SHORT_KEY] = str(PER_15MIN_LIMIT)
        mock_redis._ttls[SHORT_KEY] = 100

        # _safe_get fonctionne mais ttl() échoue au 2e appel (celui dans check_and_wait)
        original_ttl = mock_redis.ttl.side_effect
        call_count = [0]

        def ttl_with_error(key):
            call_count[0] += 1
            # Les premiers appels de _safe_get fonctionnent normalement
            # L'appel dans check_and_wait_if_needed échoue
            if key == SHORT_KEY and call_count[0] > 2:
                raise redis.RedisError("Timeout")
            return original_ttl(key)

        mock_redis.ttl.side_effect = ttl_with_error
        result = manager.check_and_wait_if_needed()
        assert result is False

    def test_no_wait_under_15min_quota(self, manager, mock_redis):
        """Sous le quota 15min → pas d'attente, retourne True directement."""
        mock_redis._store[DAILY_KEY] = "10"
        mock_redis._ttls[DAILY_KEY] = 100
        mock_redis._store[SHORT_KEY] = str(PER_15MIN_LIMIT - 1)
        mock_redis._ttls[SHORT_KEY] = 100
        assert manager.check_and_wait_if_needed() is True


# ---------------------------------------------------------------
# increment_usage
# ---------------------------------------------------------------

class TestIncrementUsage:

    def test_increments_both_counters(self, manager, mock_redis):
        manager.increment_usage()
        assert mock_redis._store[DAILY_KEY] == "1"
        assert mock_redis._store[SHORT_KEY] == "1"

    def test_increments_are_cumulative(self, manager, mock_redis):
        # Simuler des TTL existants après le 1er appel
        manager.increment_usage()
        mock_redis._ttls[DAILY_KEY] = 3000
        mock_redis._ttls[SHORT_KEY] = 800
        manager.increment_usage()
        manager.increment_usage()
        assert mock_redis._store[DAILY_KEY] == "3"
        assert mock_redis._store[SHORT_KEY] == "3"

    def test_sets_ttl_on_first_increment(self, manager, mock_redis):
        manager.increment_usage()
        assert SHORT_KEY in mock_redis._ttls
        assert mock_redis._ttls[SHORT_KEY] == 900
        assert DAILY_KEY in mock_redis._ttls
        assert mock_redis._ttls[DAILY_KEY] >= 1


# ---------------------------------------------------------------
# get_status
# ---------------------------------------------------------------

class TestGetStatus:

    def test_returns_all_expected_keys(self, manager, mock_redis):
        status = manager.get_status()
        assert "daily_used" in status
        assert "daily_limit" in status
        assert "per_15min_used" in status
        assert "per_15min_limit" in status
        assert "next_15min_reset" in status
        assert "daily_reset" in status

    def test_returns_correct_values(self, manager, mock_redis):
        mock_redis._store[DAILY_KEY] = "42"
        mock_redis._ttls[DAILY_KEY] = 5000
        mock_redis._store[SHORT_KEY] = "7"
        mock_redis._ttls[SHORT_KEY] = 300
        status = manager.get_status()
        assert status["daily_used"] == 42
        assert status["daily_limit"] == DAILY_LIMIT
        assert status["per_15min_used"] == 7
        assert status["per_15min_limit"] == PER_15MIN_LIMIT

    def test_returns_correct_limits(self, manager):
        status = manager.get_status()
        assert status["daily_limit"] == 1000
        assert status["per_15min_limit"] == 100

    def test_reset_times_are_in_future(self, manager, mock_redis):
        mock_redis._store[DAILY_KEY] = "1"
        mock_redis._ttls[DAILY_KEY] = 5000
        mock_redis._store[SHORT_KEY] = "1"
        mock_redis._ttls[SHORT_KEY] = 300
        status = manager.get_status()
        now = datetime.now(timezone.utc)
        assert status["next_15min_reset"] > now
        assert status["daily_reset"] > now

    def test_reset_times_fallback_when_no_ttl(self, manager, mock_redis):
        """Sans clé existante → les resets sont calculés par défaut."""
        status = manager.get_status()
        now = datetime.now(timezone.utc)
        # daily_reset ≈ prochain minuit UTC
        assert status["daily_reset"] > now
        # next_15min_reset ≈ now + 15 min
        assert status["next_15min_reset"] > now
        assert status["next_15min_reset"] < now + timedelta(minutes=16)

    def test_get_status_redis_down(self, manager, mock_redis):
        """Redis down → retourne quand même un status avec des valeurs par défaut."""
        mock_redis.get.side_effect = redis.RedisError("Down")
        mock_redis.ttl.side_effect = redis.RedisError("Down")
        status = manager.get_status()
        assert status["daily_used"] == 0
        assert status["per_15min_used"] == 0
        assert status["daily_limit"] == DAILY_LIMIT


# ---------------------------------------------------------------
# Résilience Redis
# ---------------------------------------------------------------

class TestRedisResilience:

    def test_manager_works_without_redis(self):
        """Un manager avec Redis=None utilise get_redis_client (lazy init)."""
        with patch("app.domain.services.redis_quota_manager.get_redis_client") as mock_get:
            mock_client = MagicMock(spec=redis.Redis)
            mock_client.get.return_value = None
            mock_client.incr.return_value = 1
            mock_client.ttl.return_value = -2
            mock_get.return_value = mock_client
            mgr = RedisQuotaManager(redis_client=None)
            mgr.increment_usage()
            mock_get.assert_called()

    def test_all_methods_handle_redis_errors(self, mock_redis):
        """Toutes les méthodes publiques doivent survivre à un Redis down."""
        mock_redis.get.side_effect = redis.RedisError("Down")
        mock_redis.set.side_effect = redis.RedisError("Down")
        mock_redis.incr.side_effect = redis.RedisError("Down")
        mock_redis.ttl.side_effect = redis.RedisError("Down")
        mock_redis.expire.side_effect = redis.RedisError("Down")

        mgr = RedisQuotaManager(redis_client=mock_redis)

        # Aucune de ces méthodes ne doit lever d'exception
        assert mgr.daily_count == 0
        assert mgr.per_15min_count == 0
        mgr.daily_count = 100  # setter silencieux
        mgr.increment_usage()
        # daily_count retourne 0 (Redis down) → < limit → retourne True
        assert mgr.check_and_wait_if_needed() is True
