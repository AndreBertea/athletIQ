"""
Client Redis pour athletIQ.
Fournit une connexion partagée et un health check.
"""
import logging
from functools import lru_cache

import redis

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache()
def get_redis_client() -> redis.Redis:
    """Retourne un client Redis connecté (singleton via lru_cache)."""
    settings = get_settings()
    return redis.Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )


def check_redis_health() -> bool:
    """Vérifie que Redis répond à un PING. Retourne True si OK, False sinon."""
    try:
        client = get_redis_client()
        return client.ping()
    except Exception as exc:
        logger.warning(f"Redis health check échoué: {exc}")
        return False
