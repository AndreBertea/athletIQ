"""
RedisQuotaManager — Gestion des quotas API Strava via Redis.

Stocke deux compteurs dans Redis :
  - strava:quota:daily   → compteur journalier (TTL = secondes jusqu'à minuit UTC)
  - strava:quota:15min   → compteur par tranche de 15 min (TTL = 900 s)

Expose la même interface que StravaQuotaManager (in-memory) pour un
remplacement transparent.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import redis

from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

DAILY_KEY = "strava:quota:daily"
SHORT_KEY = "strava:quota:15min"

DAILY_LIMIT = 1000
PER_15MIN_LIMIT = 100


def _seconds_until_midnight_utc() -> int:
    """Nombre de secondes restantes jusqu'au prochain minuit UTC.

    Retourne au minimum 1 pour éviter un TTL de 0 (suppression immédiate)
    si l'appel tombe pile à minuit.
    """
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((midnight - now).total_seconds()), 1)


class RedisQuotaManager:
    """Gestionnaire des quotas API Strava avec compteurs Redis."""

    def __init__(self, redis_client: redis.Redis | None = None):
        self._redis: redis.Redis | None = redis_client
        self.daily_limit = DAILY_LIMIT
        self.per_15min_limit = PER_15MIN_LIMIT

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_redis(self) -> redis.Redis:
        """Retourne le client Redis (lazy init)."""
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    def _safe_get(self, key: str) -> int:
        """Lit un compteur Redis ; retourne 0 si la clé n'existe pas ou si Redis est down."""
        try:
            r = self._get_redis()
            val = r.get(key)
            if val is None:
                return 0
            # Filet de sécurité : corriger une clé orpheline (sans TTL)
            if r.ttl(key) == -1:
                default_ttl = 900 if key == SHORT_KEY else _seconds_until_midnight_utc()
                logger.warning(f"Clé {key} sans TTL détectée (lecture), réapplication de {default_ttl}s")
                r.expire(key, default_ttl)
            return int(val)
        except redis.RedisError as exc:
            logger.warning(f"Redis indisponible (lecture {key}): {exc}")
            return 0

    def _safe_incr(self, key: str, ttl: int) -> int:
        """Incrémente un compteur atomiquement avec TTL garanti.

        Utilise un pipeline Redis pour poser le TTL de façon fiable :
        - À la création (new_val == 1) : pose le TTL initial.
        - Filet de sécurité : si la clé existe sans TTL (crash entre INCR et EXPIRE),
          le TTL est réappliqué pour éviter une clé orpheline qui persiste indéfiniment.
        """
        try:
            r = self._get_redis()
            new_val = r.incr(key)
            if new_val == 1:
                r.expire(key, ttl)
            elif r.ttl(key) == -1:
                # Clé sans TTL (orpheline) → réappliquer le TTL
                logger.warning(f"Clé {key} sans TTL détectée, réapplication de {ttl}s")
                r.expire(key, ttl)
            return new_val
        except redis.RedisError as exc:
            logger.warning(f"Redis indisponible (incr {key}): {exc}")
            return 0

    # ------------------------------------------------------------------
    # Propriétés de compatibilité
    # ------------------------------------------------------------------

    @property
    def daily_count(self) -> int:
        return self._safe_get(DAILY_KEY)

    @daily_count.setter
    def daily_count(self, value: int) -> None:
        """Permet de forcer le compteur (ex: quand Strava renvoie 429)."""
        try:
            r = self._get_redis()
            ttl = r.ttl(DAILY_KEY)
            r.set(DAILY_KEY, value)
            if ttl and ttl > 0:
                r.expire(DAILY_KEY, ttl)
            else:
                r.expire(DAILY_KEY, _seconds_until_midnight_utc())
        except redis.RedisError as exc:
            logger.warning(f"Redis indisponible (set daily_count): {exc}")

    @property
    def per_15min_count(self) -> int:
        return self._safe_get(SHORT_KEY)

    # ------------------------------------------------------------------
    # Interface publique (identique à StravaQuotaManager)
    # ------------------------------------------------------------------

    def check_and_wait_if_needed(self) -> bool:
        """Vérifie les quotas et attend si nécessaire. Retourne False si quota daily atteint."""
        daily = self.daily_count
        if daily >= self.daily_limit:
            logger.warning("Quota journalier Strava atteint")
            return False

        short = self.per_15min_count
        if short >= self.per_15min_limit:
            # Attendre le temps restant du TTL de la clé 15min
            try:
                ttl = self._get_redis().ttl(SHORT_KEY)
            except redis.RedisError:
                ttl = 60  # fallback raisonnable
            wait_time = max(ttl, 1)
            logger.info(f"Quota 15min atteint, attente de {wait_time}s")
            time.sleep(wait_time)

        return True

    def increment_usage(self) -> None:
        """Incrémente les deux compteurs atomiquement."""
        self._safe_incr(DAILY_KEY, _seconds_until_midnight_utc())
        self._safe_incr(SHORT_KEY, 900)  # 15 minutes

    def get_status(self) -> Dict[str, Any]:
        """Retourne le statut des quotas (compatible avec l'ancien format)."""
        now = datetime.now(timezone.utc)

        # Calculer les dates de reset à partir des TTL Redis
        try:
            r = self._get_redis()
            daily_ttl = r.ttl(DAILY_KEY)
            short_ttl = r.ttl(SHORT_KEY)
        except redis.RedisError:
            daily_ttl = -1
            short_ttl = -1

        if daily_ttl and daily_ttl > 0:
            daily_reset = now + timedelta(seconds=daily_ttl)
        else:
            daily_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        if short_ttl and short_ttl > 0:
            next_15min_reset = now + timedelta(seconds=short_ttl)
        else:
            next_15min_reset = now + timedelta(minutes=15)

        return {
            "daily_used": self.daily_count,
            "daily_limit": self.daily_limit,
            "per_15min_used": self.per_15min_count,
            "per_15min_limit": self.per_15min_limit,
            "next_15min_reset": next_15min_reset,
            "daily_reset": daily_reset,
        }
