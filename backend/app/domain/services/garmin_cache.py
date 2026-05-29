"""
Service de cache en mémoire pour les tokens Garmin.
Évite les re-authentifications inutiles et les appels API répétés.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class GarminTokenCache:
    """Cache en mémoire pour les tokens Garmin par utilisateur."""

    def __init__(self, ttl_minutes: int = 120):
        self.ttl = timedelta(minutes=ttl_minutes)
        self._cache: dict[str, dict] = {}

    def get(self, user_id: UUID) -> Optional[str]:
        """Récupère un token Garmin du cache s'il est valide."""
        user_str = str(user_id)
        if user_str not in self._cache:
            return None

        entry = self._cache[user_str]
        if datetime.utcnow() > entry["expires_at"]:
            del self._cache[user_str]
            logger.info(f"Token Garmin expiré pour user {user_id}")
            return None

        logger.debug(f"Token Garmin récupéré du cache pour user {user_id}")
        return entry["token"]

    def set(self, user_id: UUID, token: str) -> None:
        """Stocke un token Garmin dans le cache."""
        user_str = str(user_id)
        self._cache[user_str] = {
            "token": token,
            "expires_at": datetime.utcnow() + self.ttl,
            "created_at": datetime.utcnow(),
        }
        logger.info(f"Token Garmin mis en cache pour user {user_id} (TTL: {self.ttl.total_seconds()/60:.0f}min)")

    def invalidate(self, user_id: UUID) -> None:
        """Supprime un token du cache (par ex. après déconnexion)."""
        user_str = str(user_id)
        if user_str in self._cache:
            del self._cache[user_str]
            logger.info(f"Token Garmin invalidé pour user {user_id}")

    def clear_all(self) -> None:
        """Vide le cache complètement."""
        self._cache.clear()
        logger.info("Cache Garmin vidé")


# Instance globale singleton
garmin_token_cache = GarminTokenCache(ttl_minutes=120)
