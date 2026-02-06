"""
Application FastAPI principale pour AthlétIQ
Point d'entrée de l'API backend
"""
import logging
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from app.core.settings import get_settings
from app.api.routes import router
from app.core.database import create_db_and_tables
from app.core.redis import check_redis_health
from app.domain.services.auto_enrichment_service import auto_enrichment_service

settings = get_settings()

# Configuration du logging conditionnée par ENVIRONMENT
_log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

_handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
if settings.ENVIRONMENT != "production":
    _handlers.append(logging.FileHandler('app.log'))

logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
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

    # Demarrer le worker d'enrichissement en arriere-plan
    auto_enrichment_service.start_worker()
    logger.info("✅ Worker d'enrichissement demarre (idle jusqu'a reception d'items)")

    yield

    # Shutdown
    auto_enrichment_service.stop_worker()
    logger.info("🛑 Worker d'enrichissement arrete")

app = FastAPI(
    title="AthlétIQ API",
    description="API pour l'analyse et le suivi des performances sportives",
    version="2.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Inclure les routes
app.include_router(router, prefix="/api/v1")

@app.get("/health")
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