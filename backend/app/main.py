"""
Application FastAPI principale pour AthlétIQ
Point d'entrée de l'API backend
"""
import logging
from logging.handlers import RotatingFileHandler
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi.errors import RateLimitExceeded
import sentry_sdk

from app.core.settings import get_settings
from app.api.routers import router, limiter
from app.core.database import create_db_and_tables
from app.core.redis import check_redis_health
from app.domain.services.auto_enrichment_service import auto_enrichment_service
from app.domain.services.livetrack_worker import livetrack_poller

settings = get_settings()

# Initialiser Sentry (uniquement si SENTRY_DSN est configure)
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.2 if settings.ENVIRONMENT == "production" else 1.0,
        send_default_pii=False,
    )

# Configuration du logging conditionnée par ENVIRONMENT
_log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

_handler = logging.StreamHandler(sys.stdout)

if settings.ENVIRONMENT == "production":
    from pythonjsonlogger import jsonlogger
    _handler.setFormatter(jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    ))
else:
    _handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

_handlers: list[logging.Handler] = [_handler]
if settings.ENVIRONMENT != "production":
    _handlers.append(RotatingFileHandler(
        'app.log', maxBytes=5_000_000, backupCount=3,
    ))

logging.basicConfig(
    level=_log_level,
    handlers=_handlers,
)

# En production, réduire le bruit des modules tiers
if settings.ENVIRONMENT == "production":
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestionnaire de cycle de vie de l'application"""
    # Startup
    logger.info("🚀 Démarrage d'AthlétIQ API v2.0.0")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    
    # Initialiser la base de données
    create_db_and_tables()
    logger.info("✅ Base de données initialisée")
    
    # Vérifier la connexion Redis
    if check_redis_health():
        logger.info("✅ Redis connecté")
    else:
        logger.warning("⚠️  Redis non disponible — les fonctionnalités dépendant de Redis seront dégradées")

    # Le worker est reserve au connecteur Strava lorsqu'il est explicitement actif.
    if settings.STRAVA_INTEGRATION_ENABLED:
        auto_enrichment_service.start_worker()
        logger.info("✅ Worker d'enrichissement Strava demarre (idle jusqu'a reception d'items)")
    else:
        logger.info("Integration Strava suspendue: worker d'enrichissement desactive")

    # Relancer les sessions LiveTrack actives (apres redemarrage backend)
    await livetrack_poller.restart_active_sessions()
    logger.info("✅ LiveTrack poller initialise")

    yield

    # Shutdown
    if settings.STRAVA_INTEGRATION_ENABLED:
        auto_enrichment_service.stop_worker()
        logger.info("🛑 Worker d'enrichissement Strava arrete")

    livetrack_poller.shutdown()
    logger.info("🛑 LiveTrack poller arrete")

app = FastAPI(
    title="AthlétIQ API",
    description="API pour l'analyse et le suivi des performances sportives",
    version="2.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan
)

# Rate limiting
app.state.limiter = limiter


async def _custom_rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Retourne un 429 propre avec headers Retry-After et X-RateLimit-*."""
    import re

    # Extraire le limite et la fenêtre temporelle depuis le detail
    # Ex: "3 per 1 hour"
    match = re.search(r"(\d+)\s+per\s+(\d+)\s+(\w+)", exc.detail)
    retry_after = "3600"  # Par défaut 1 heure en secondes

    if match:
        count, window, unit = match.groups()
        if unit.lower() == "hour" or unit.lower() == "hours":
            retry_after = str(int(window) * 3600)
        elif unit.lower() == "minute" or unit.lower() == "minutes":
            retry_after = str(int(window) * 60)

    response = JSONResponse(
        status_code=429,
        content={
            "detail": "Trop de requetes - Connexion Garmin limitée à 5/heure pour sécurité",
            "message": f"Réessayez dans {retry_after} secondes",
            "retry_after": int(retry_after),
        },
    )
    response.headers["Retry-After"] = retry_after

    try:
        if hasattr(request.state, 'view_rate_limit'):
            response = request.app.state.limiter._inject_headers(
                response, request.state.view_rate_limit
            )
    except Exception as e:
        logger.warning(f"Impossible d'injecter les headers de rate limit: {e}")

    return response


app.add_exception_handler(RateLimitExceeded, _custom_rate_limit_handler)

# Middlewares de securite en production
if settings.ENVIRONMENT == "production":
    class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            if request.headers.get("x-forwarded-proto") == "http":
                url = request.url.replace(scheme="https")
                return RedirectResponse(url, status_code=301)
            return await call_next(request)

    class SecureCookiesMiddleware(BaseHTTPMiddleware):
        """Force le flag Secure sur tous les cookies en production."""
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            if "set-cookie" in response.headers:
                new_cookies = []
                for header_value in response.headers.getlist("set-cookie"):
                    if "; secure" not in header_value.lower():
                        header_value += "; Secure"
                    new_cookies.append(header_value)
                del response.headers["set-cookie"]
                for cookie in new_cookies:
                    response.headers.append("set-cookie", cookie)
            return response

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        """Ajoute les headers de securite sur toutes les reponses en production."""
        async def dispatch(self, request: Request, call_next):
            response = await call_next(request)
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            return response

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(SecureCookiesMiddleware)
    app.add_middleware(HTTPSRedirectMiddleware)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Inclure les routes
app.include_router(router, prefix="/api/v1")

@app.get("/health")
@limiter.exempt
async def health_check():
    """Point de santé de l'API"""
    redis_ok = check_redis_health()
    status = "healthy" if redis_ok else "degraded"
    return JSONResponse(
        content={
            "status": status,
            "version": "2.0.0",
            "environment": settings.ENVIRONMENT,
            "services": {
                "redis": "connected" if redis_ok else "disconnected",
            },
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc):
    """Gestionnaire global des exceptions"""
    logger.error(f"Erreur non gérée: {type(exc).__name__}: {str(exc)}", exc_info=True)
    if settings.DEBUG:
        content = {
            "detail": "Erreur interne du serveur",
            "type": type(exc).__name__,
            "message": str(exc),
        }
    else:
        content = {
            "detail": "Erreur interne du serveur",
            "message": "Une erreur s'est produite",
        }
    return JSONResponse(status_code=500, content=content)

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Lancement de l'application sur le port 8000")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    ) 
