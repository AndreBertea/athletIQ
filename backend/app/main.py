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
from app.domain.services.auto_enrichment_service import auto_enrichment_service

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('app.log') if hasattr(logging, 'FileHandler') else logging.StreamHandler(sys.stdout)
    ]
)

# Réduire le niveau de logging pour certains modules verbeux
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

settings = get_settings()

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
    
    # NE PAS démarrer l'enrichissement automatique par défaut
    # Il sera démarré manuellement via l'API quand nécessaire
    logger.info("⏸️  Service d'enrichissement automatique disponible (démarrage manuel)")
    
    yield
    
    # Shutdown
    auto_enrichment_service.stop_background_enrichment()
    logger.info("🛑 Service d'enrichissement automatique arrêté")

app = FastAPI(
    title="AthlétIQ API",
    description="API pour l'analyse et le suivi des performances sportives",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permettre toutes les origines pour le développement
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Gestionnaire OPTIONS global pour CORS preflight
@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    """Gestionnaire pour les requêtes OPTIONS (preflight CORS)"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "600",
        }
    )

# Inclure les routes
app.include_router(router, prefix="/api/v1")

@app.get("/health")
async def health_check():
    """Point de santé de l'API"""
    return JSONResponse(
        content={
            "status": "healthy",
            "version": "2.0.0",
            "environment": settings.ENVIRONMENT
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc):
    """Gestionnaire global des exceptions"""
    logger.error(f"Erreur non gérée: {type(exc).__name__}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Erreur interne du serveur",
            "type": type(exc).__name__,
            "message": str(exc) if settings.DEBUG else "Une erreur s'est produite"
        }
    )

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Lancement de l'application sur le port 8000")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    ) 