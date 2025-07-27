"""
Routes API principales pour AthlétIQ
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Form, File, UploadFile
from fastapi.security import HTTPBearer
from fastapi.responses import RedirectResponse, JSONResponse
from sqlmodel import Session, select, func
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime, timedelta
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

def extract_token_from_credentials(token_credentials) -> str:
    """Extrait le token de l'objet credentials"""
    if hasattr(token_credentials, 'credentials'):
        return token_credentials.credentials
    return str(token_credentials)

from app.core.database import get_session
from app.auth.jwt import jwt_manager, password_manager, TokenResponse, get_current_user_id
from app.auth.strava_oauth import strava_oauth, StravaTokens
from app.auth.google_oauth import google_oauth
from app.domain.entities import User, UserCreate, UserRead, UserUpdate, StravaAuth, GoogleAuth, Activity, ActivityRead, ActivityCreate, ActivityWithStreams, ActivityStats, WorkoutPlan, WorkoutPlanRead, WorkoutPlanCreate, WorkoutPlanUpdate
from app.domain.entities.workout_plan import WorkoutType
from app.domain.services.analysis_service import AnalysisService
from app.domain.services.strava_sync_service import strava_sync_service
from app.domain.services.csv_import_service import csv_import_service
from app.domain.services.detailed_strava_service import detailed_strava_service
from app.domain.services.auto_enrichment_service import auto_enrichment_service
from app.domain.services.google_calendar_service import google_calendar_service

router = APIRouter()
security = HTTPBearer()

# Initialiser les services
analysis_service = AnalysisService()


# ============ AUTHENTIFICATION ============

# ============ GOOGLE OAUTH ============

@router.get("/auth/google/login")
async def google_login():
    """Redirige vers l'autorisation Google OAuth"""
    try:
        logger.info("Génération de l'URL d'autorisation Google...")
        auth_url = google_oauth.get_authorization_url()
        logger.info(f"URL d'autorisation générée: {auth_url}")
        return {"auth_url": auth_url}
    except Exception as e:
        logger.error(f"Erreur lors de la génération de l'URL d'autorisation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération de l'URL d'autorisation: {str(e)}"
        )


@router.get("/auth/google/status")
async def google_status(
    token_credentials: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Vérifie le statut de la connexion Google OAuth"""
    try:
        # Extraire le token de l'objet credentials
        token = token_credentials.credentials if hasattr(token_credentials, 'credentials') else str(token_credentials)
        user_id = get_current_user_id(token)
        
        # Vérifier si l'utilisateur a une authentification Google
        google_auth = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()
        
        if not google_auth:
            return {
                "connected": False,
                "google_user_id": None,
                "scope": None,
                "expires_at": None,
                "is_expired": True
            }
        
        # Vérifier si le token a expiré
        is_expired = google_auth.expires_at < datetime.now() if google_auth.expires_at else True
        
        return {
            "connected": True,
            "google_user_id": google_auth.user_id,
            "scope": google_auth.scope,
            "expires_at": google_auth.expires_at.isoformat() if google_auth.expires_at else None,
            "is_expired": is_expired
        }
        
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du statut Google: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la vérification du statut Google"
        )


@router.post("/auth/google/refresh")
async def google_refresh_token(
    token_credentials: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Rafraîchit automatiquement le token Google OAuth"""
    try:
        # Extraire le token de l'objet credentials
        token = token_credentials.credentials if hasattr(token_credentials, 'credentials') else str(token_credentials)
        user_id = get_current_user_id(token)
        
        # Récupérer l'authentification Google
        google_auth = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()
        
        if not google_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Aucune authentification Google trouvée"
            )
        
        # Déchiffrer le refresh token
        from app.auth.google_oauth import google_oauth
        refresh_token = google_oauth.decrypt_token(google_auth.refresh_token_encrypted)
        
        # Rafraîchir le token
        new_tokens = google_oauth.refresh_access_token(refresh_token)
        
        # Chiffrer et sauvegarder les nouveaux tokens
        encrypted_access_token = google_oauth.encrypt_token(new_tokens.access_token)
        encrypted_refresh_token = google_oauth.encrypt_token(new_tokens.refresh_token)
        
        # Mettre à jour en base de données
        google_auth.access_token_encrypted = encrypted_access_token
        google_auth.refresh_token_encrypted = encrypted_refresh_token
        google_auth.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
        google_auth.updated_at = datetime.now()
        
        session.add(google_auth)
        session.commit()
        
        return {
            "success": True,
            "message": "Token rafraîchi avec succès",
            "expires_at": google_auth.expires_at.isoformat(),
            "is_expired": False
        }
        
    except Exception as e:
        logger.error(f"Erreur lors du refresh du token Google: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du refresh du token: {str(e)}"
        )


@router.get("/auth/google/callback")
async def google_callback(
    code: str = Query(...),
    session: Session = Depends(get_session)
):
    """Callback Google OAuth - échange le code contre des tokens"""
    try:
        # Échanger le code contre des tokens
        tokens = google_oauth.exchange_code_for_tokens(code)
        
        # Récupérer les informations utilisateur
        user_info = google_oauth.get_user_info(tokens.access_token)
        
        # Créer ou récupérer l'utilisateur
        user = session.exec(
            select(User).where(User.email == user_info['email'])
        ).first()
        
        if not user:
            # Créer un nouvel utilisateur
            user = User(
                email=user_info['email'],
                full_name=user_info.get('name', ''),
                is_active=True
            )
            session.add(user)
            session.commit()
            session.refresh(user)
        
        # Chiffrer les tokens avant de les sauvegarder
        encrypted_access_token = google_oauth.encrypt_token(tokens.access_token)
        encrypted_refresh_token = google_oauth.encrypt_token(tokens.refresh_token)
        
        # Sauvegarder les tokens Google
        google_auth = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == user.id)
        ).first()
        
        if google_auth:
            # Mettre à jour les tokens existants
            google_auth.access_token_encrypted = encrypted_access_token
            google_auth.refresh_token_encrypted = encrypted_refresh_token
            google_auth.expires_at = datetime.fromtimestamp(tokens.expires_at)
            google_auth.scope = tokens.scope
            google_auth.google_user_id = tokens.google_user_id
        else:
            # Créer une nouvelle entrée
            google_auth = GoogleAuth(
                user_id=user.id,
                google_user_id=tokens.google_user_id,
                access_token_encrypted=encrypted_access_token,
                refresh_token_encrypted=encrypted_refresh_token,
                expires_at=datetime.fromtimestamp(tokens.expires_at),
                scope=tokens.scope
            )
            session.add(google_auth)
        
        session.commit()
        
        # Générer les tokens JWT
        jwt_tokens = jwt_manager.create_token_pair(str(user.id), user.email)
        
        # Rediriger vers le frontend avec les tokens
        frontend_url = "http://localhost:3000"
        return RedirectResponse(
            url=f"{frontend_url}/google-connect?success=true&google_user_id={tokens.google_user_id}&access_token={jwt_tokens.access_token}&refresh_token={jwt_tokens.refresh_token}"
        )
        
    except Exception as e:
        logger.error(f"Erreur lors de l'authentification Google: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de l'authentification Google: {str(e)}"
        )


@router.post("/auth/signup", response_model=TokenResponse)
async def signup(
    user_data: UserCreate,
    session: Session = Depends(get_session)
):
    """Inscription d'un nouvel utilisateur"""
    # Vérifier si l'email existe déjà
    existing_user = session.exec(
        select(User).where(User.email == user_data.email)
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Créer l'utilisateur
    hashed_password = password_manager.hash_password(user_data.password)
    db_user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hashed_password
    )
    
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    
    # Générer les tokens
    return jwt_manager.create_token_pair(str(db_user.id), db_user.email)


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    """Connexion utilisateur"""
    user = session.exec(
        select(User).where(User.email == email)
    ).first()
    
    if not user or not password_manager.verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    return jwt_manager.create_token_pair(str(user.id), user.email)


# Temporairement commenté pour résoudre le conflit de paramètres
# @router.post("/auth/refresh", response_model=dict)
# async def refresh_token(refresh_token_param: str = Form(..., alias="refresh_token")):
#     """Rafraîchit l'access token"""
#     new_access_token = jwt_manager.refresh_access_token(refresh_token_param)
#     return {"access_token": new_access_token, "token_type": "bearer"}


@router.get("/auth/me", response_model=UserRead)
async def get_current_user(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Récupère les informations de l'utilisateur connecté"""
    user_id = get_current_user_id(token.credentials)
    user = session.get(User, UUID(user_id))
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


# ============ OAUTH STRAVA ============

@router.get("/auth/strava/login")
async def strava_login(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Initie la connexion OAuth Strava"""
    user_id = get_current_user_id(token.credentials)
    
    # Utiliser l'user_id comme state pour la sécurité
    auth_url = strava_oauth.get_authorization_url(state=user_id)
    
    return {"authorization_url": auth_url}


@router.get("/auth/strava/callback")
async def strava_callback(
    request: Request,
    session: Session = Depends(get_session)
):
    """Callback OAuth Strava - Traite l'authentification et redirige"""
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Récupérer les paramètres de l'URL
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")
    scope = params.get("scope")
    error = params.get("error")
    
    logger.info(f"Callback Strava reçu avec params: code={'***' if code else None}, state={state}, error={error}")
    
    # Gérer les erreurs OAuth
    if error:
        logger.error(f"Erreur OAuth reçue de Strava: {error}")
        frontend_url = f"http://localhost:3000/strava-connect?error=oauth_error&message={error}"
        return RedirectResponse(url=frontend_url)
    
    if not code:
        logger.error("Code d'autorisation manquant dans le callback")
        frontend_url = "http://localhost:3000/strava-connect?error=no_code&message=Code d'autorisation manquant"
        return RedirectResponse(url=frontend_url)
    
    try:
        logger.info("Début échange code contre tokens...")
        # Échanger le code contre les tokens
        tokens = strava_oauth.exchange_code_for_tokens(code)
        logger.info(f"Tokens reçus pour l'athlète {tokens.athlete_id}")
        
        # Si pas de state, on ne peut pas identifier l'utilisateur
        if not state:
            logger.error("State manquant dans le callback")
            frontend_url = "http://localhost:3000/strava-connect?error=no_state&message=Paramètre d'état manquant"
            return RedirectResponse(url=frontend_url)
        
        # Récupérer l'utilisateur
        try:
            user = session.get(User, UUID(state))
            logger.info(f"Utilisateur trouvé: {user.email if user else 'None'}")
        except ValueError as e:
            logger.error(f"State invalide: {state}, erreur: {e}")
            frontend_url = "http://localhost:3000/strava-connect?error=invalid_state&message=Identifiant d'état invalide"
            return RedirectResponse(url=frontend_url)
        
        if not user:
            logger.error(f"Utilisateur non trouvé pour state: {state}")
            frontend_url = "http://localhost:3000/strava-connect?error=user_not_found&message=Utilisateur non trouvé"
            return RedirectResponse(url=frontend_url)
        
        # Chiffrer les tokens
        logger.info("Chiffrement des tokens...")
        encrypted_access = strava_oauth.encrypt_token(tokens.access_token)
        encrypted_refresh = strava_oauth.encrypt_token(tokens.refresh_token)
        logger.info("Tokens chiffrés avec succès")
        
        # Sauvegarder ou mettre à jour l'auth Strava
        logger.info("Sauvegarde en base de données...")
        existing_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == user.id)
        ).first()
        
        if existing_auth:
            logger.info("Mise à jour de l'authentification Strava existante")
            existing_auth.access_token_encrypted = encrypted_access
            existing_auth.refresh_token_encrypted = encrypted_refresh
            existing_auth.expires_at = datetime.fromtimestamp(tokens.expires_at)
            existing_auth.scope = tokens.scope
            existing_auth.updated_at = datetime.utcnow()
        else:
            logger.info("Création nouvelle authentification Strava")
            strava_auth = StravaAuth(
                user_id=user.id,
                strava_athlete_id=tokens.athlete_id,
                access_token_encrypted=encrypted_access,
                refresh_token_encrypted=encrypted_refresh,
                expires_at=datetime.fromtimestamp(tokens.expires_at),
                scope=tokens.scope
            )
            session.add(strava_auth)
        
        session.commit()
        logger.info("Données sauvegardées en base")
        
        # Rediriger vers le frontend avec succès
        frontend_url = f"http://localhost:3000/strava-connect?success=true&athlete_id={tokens.athlete_id}"
        logger.info(f"Redirection vers: {frontend_url}")
        return RedirectResponse(url=frontend_url)
        
    except Exception as e:
        # Log détaillé de l'erreur
        logger.error(f"Erreur dans le callback Strava: {type(e).__name__}: {str(e)}", exc_info=True)
        # Rediriger vers le frontend avec l'erreur détaillée
        error_msg = f"{type(e).__name__}: {str(e)}"
        error_msg_encoded = error_msg.replace(" ", "%20").replace(":", "%3A")
        frontend_url = f"http://localhost:3000/strava-connect?error=callback_error&message={error_msg_encoded}"
        return RedirectResponse(url=frontend_url)


@router.get("/auth/strava/status")
async def strava_status(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Vérifie le statut de connexion Strava"""
    user_id = get_current_user_id(token.credentials)
    
    strava_auth = session.exec(
        select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
    ).first()
    
    if not strava_auth:
        return {"connected": False}
    
    is_expired = strava_oauth.is_token_expired(strava_auth.expires_at)
    
    return {
        "connected": True,
        "athlete_id": strava_auth.strava_athlete_id,
        "scope": strava_auth.scope,
        "expires_at": strava_auth.expires_at,
        "is_expired": is_expired,
        "last_sync": strava_auth.updated_at
    }


# ============ ACTIVITÉS ============

@router.get("/activities", response_model=List[ActivityRead])
async def get_activities(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    activity_type: Optional[str] = None
):
    """Récupère les activités de l'utilisateur"""
    user_id = get_current_user_id(token.credentials)
    
    query = select(Activity).where(Activity.user_id == UUID(user_id))
    
    if activity_type:
        if activity_type == "running_activities":
            # Filtre spécial pour toutes les activités de course
            from app.domain.entities.activity import ActivityType
            query = query.where(Activity.activity_type.in_([ActivityType.RUN, ActivityType.TRAIL_RUN]))
        else:
            query = query.where(Activity.activity_type == activity_type)
    
    query = query.offset(offset).limit(limit).order_by(Activity.start_date.desc())
    
    activities = session.exec(query).all()
    return activities


@router.get("/activities/stats", response_model=ActivityStats)
async def get_activity_stats(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    period_days: int = Query(default=30, ge=1, le=365)
):
    """Récupère les statistiques d'activités"""
    user_id = get_current_user_id(token.credentials)
    
    # Filtrer par période
    cutoff_date = datetime.utcnow() - timedelta(days=period_days)
    activities = session.exec(
        select(Activity).where(
            Activity.user_id == UUID(user_id),
            Activity.start_date >= cutoff_date
        )
    ).all()
    
    if not activities:
        return ActivityStats(
            total_activities=0,
            total_distance=0,
            total_time=0,
            average_pace=0,
            activities_by_type={},
            distance_by_month={}
        )
    
    # Calculs statistiques
    total_distance = sum(act.distance for act in activities) / 1000  # km
    total_time = sum(act.moving_time for act in activities)
    
    # Calculer l'allure moyenne en pondérant par la distance
    total_weighted_pace = 0
    total_distance_with_pace = 0
    
    for activity in activities:
        if activity.average_pace and activity.distance > 0:
            distance_km = activity.distance / 1000
            total_weighted_pace += activity.average_pace * distance_km
            total_distance_with_pace += distance_km
    
    avg_pace = total_weighted_pace / total_distance_with_pace if total_distance_with_pace > 0 else 0
    
    # Grouper par type
    activities_by_type = {}
    for activity in activities:
        act_type = activity.activity_type.value
        activities_by_type[act_type] = activities_by_type.get(act_type, 0) + 1
    
    # Grouper par mois
    distance_by_month = {}
    for activity in activities:
        month_key = activity.start_date.strftime("%Y-%m")
        distance_by_month[month_key] = distance_by_month.get(month_key, 0) + (activity.distance / 1000)
    
    return ActivityStats(
        total_activities=len(activities),
        total_distance=round(total_distance, 1),
        total_time=total_time,
        average_pace=round(avg_pace, 2),
        activities_by_type=activities_by_type,
        distance_by_month=distance_by_month
    )


@router.get("/activities/enrichment-status")
async def get_enrichment_status(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Récupère les vraies statistiques d'enrichissement"""
    try:
        # Connexion aux deux bases
        stridedelta_engine = create_engine("sqlite:///stridedelta.db")
        activity_detail_engine = create_engine("sqlite:///activity_detail.db")
        
        # Compter les activités dans stridedelta.db
        with stridedelta_engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count FROM activity"))
            strava_activities = result.fetchone().count
        
        # Compter les activités enrichies dans activity_detail.db
        with activity_detail_engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) as count FROM activities"))
            enriched_activities = result.fetchone().count
        
        # Calculer les statistiques
        pending_activities = max(0, strava_activities - enriched_activities)
        enrichment_percentage = round((enriched_activities / strava_activities) * 100) if strava_activities > 0 else 0
        
        # Simuler les quotas API (pour l'instant)
        quota_status = {
            "per_15min_used": 0,
            "per_15min_limit": 100,
            "daily_used": 0,
            "daily_limit": 1000,
            "next_15min_reset": "2024-01-01T00:00:00Z",
            "daily_reset": "2024-01-01T00:00:00Z"
        }
        
        return {
            "strava_activities": strava_activities,
            "enriched_activities": enriched_activities,
            "pending_activities": pending_activities,
            "enrichment_percentage": enrichment_percentage,
            "quota_status": quota_status,
            "can_enrich_more": True
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul statut enrichissement: {str(e)}")


# ============ ENDPOINTS DONNÉES ENRICHIES ============

@router.get("/activities/enriched")
async def get_enriched_activities(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sport_type: Optional[str] = Query(None)
):
    """Récupère les activités enrichies depuis activity_detail.db"""
    try:
        # Connexion à la base enrichie
        engine = create_engine("sqlite:///activity_detail.db")
        
        query = """
            SELECT 
                activity_id, name, sport_type, distance_m, moving_time_s,
                elapsed_time_s, elev_gain_m, start_date_utc, visibility,
                private, avg_speed_m_s, max_speed_m_s, avg_heartrate_bpm,
                max_heartrate_bpm, calories_kcal, description
            FROM activities
        """
        
        params = {}
        if sport_type:
            query += " WHERE sport_type = :sport_type"
            params["sport_type"] = sport_type
            
        query += " ORDER BY start_date_utc DESC LIMIT :limit OFFSET :offset"
        params.update({"limit": limit, "offset": offset})
        
        with engine.connect() as conn:
            result = conn.execute(text(query), params)
            activities = [dict(row._mapping) for row in result]
            
        # Retourner directement le tableau d'activités
        return activities
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération activités enrichies: {str(e)}")

@router.get("/activities/enriched/stats")
async def get_enriched_activity_stats(
    period_days: int = Query(30, ge=1, le=365)
):
    """Récupère les statistiques des activités enrichies"""
    try:
        engine = create_engine("sqlite:///activity_detail.db")
        
        # Date limite pour la période
        cutoff_date = datetime.now() - timedelta(days=period_days)
        
        # Récupérer les activités individuelles pour permettre l'agrégation côté frontend
        activities_query = """
            SELECT 
                activity_id, name, sport_type, distance_m, moving_time_s,
                start_date_utc, elev_gain_m, avg_speed_m_s, avg_heartrate_bpm
            FROM activities 
            WHERE start_date_utc >= :cutoff_date
            ORDER BY start_date_utc DESC
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(activities_query), {"cutoff_date": cutoff_date.isoformat()})
            activities = [dict(row._mapping) for row in result]
        
        # Calculer les statistiques agrégées
        total_activities = len(activities)
        total_distance_km = sum(act["distance_m"] or 0 for act in activities) / 1000
        total_time_hours = sum(act["moving_time_s"] or 0 for act in activities) / 3600
        
        # Répartition par type de sport
        activities_by_sport_type = {}
        distance_by_sport_type = {}
        time_by_sport_type = {}
        
        for activity in activities:
            sport_type = activity["sport_type"]
            if sport_type not in activities_by_sport_type:
                activities_by_sport_type[sport_type] = 0
                distance_by_sport_type[sport_type] = 0
                time_by_sport_type[sport_type] = 0
            
            activities_by_sport_type[sport_type] += 1
            distance_by_sport_type[sport_type] += (activity["distance_m"] or 0) / 1000
            time_by_sport_type[sport_type] += (activity["moving_time_s"] or 0) / 3600
        
        return {
            "total_activities": total_activities,
            "total_distance_km": total_distance_km,
            "total_time_hours": total_time_hours,
            "activities_by_sport_type": activities_by_sport_type,
            "distance_by_sport_type": distance_by_sport_type,
            "time_by_sport_type": time_by_sport_type,
            "activities": activities  # Ajouter les activités individuelles
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul statistiques enrichies: {str(e)}")

@router.get("/activities/enriched/{activity_id}")
async def get_enriched_activity(
    activity_id: int
):
    """Récupère une activité enrichie spécifique"""
    try:
        engine = create_engine("sqlite:///activity_detail.db")
        
        query = """
            SELECT 
                activity_id, name, sport_type, distance_m, moving_time_s,
                elapsed_time_s, elev_gain_m, start_date_utc, visibility,
                private, avg_speed_m_s, max_speed_m_s, avg_heartrate_bpm,
                max_heartrate_bpm, calories_kcal, description
            FROM activities 
            WHERE activity_id = :activity_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {"activity_id": activity_id})
            activity = result.fetchone()
            
        if not activity:
            raise HTTPException(status_code=404, detail="Activité enrichie non trouvée")
            
        return dict(activity._mapping)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération activité enrichie: {str(e)}")

@router.get("/activities/enriched/{activity_id}/streams")
async def get_enriched_activity_streams(
    activity_id: int
):
    """Récupère les streams d'une activité enrichie (heartrate, time, distance, etc.)"""
    try:
        engine = create_engine("sqlite:///activity_detail.db")
        
        query = """
            SELECT stream_type, data
            FROM activity_streams
            WHERE activity_id = :activity_id
        """
        
        with engine.connect() as conn:
            result = conn.execute(text(query), {"activity_id": activity_id})
            streams = [dict(row._mapping) for row in result]
            
        if not streams:
            raise HTTPException(status_code=404, detail="Aucun stream trouvé pour cette activité")
        
        # Convertir en dictionnaire pour faciliter l'accès
        streams_dict = {}
        for stream in streams:
            import json
            try:
                streams_dict[stream['stream_type']] = json.loads(stream['data'])
            except json.JSONDecodeError:
                streams_dict[stream['stream_type']] = []
        
        return {
            "activity_id": activity_id,
            "streams": streams_dict
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur récupération streams: {str(e)}")


@router.get("/activities/{activity_id}", response_model=ActivityWithStreams)
async def get_activity(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Récupère une activité avec ses données détaillées"""
    user_id = get_current_user_id(token.credentials)
    
    activity = session.exec(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == UUID(user_id)
        )
    ).first()
    
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activity not found"
        )
    
    return activity


# ============ PLANS D'ENTRAÎNEMENT ============

@router.post("/workout-plans", response_model=WorkoutPlanRead)
async def create_workout_plan(
    plan_data: WorkoutPlanCreate,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Crée un nouveau plan d'entraînement"""
    user_id = get_current_user_id(token.credentials)
    
    workout_plan = WorkoutPlan(
        user_id=UUID(user_id),
        **plan_data.dict()
    )
    
    session.add(workout_plan)
    session.commit()
    session.refresh(workout_plan)
    
    return workout_plan


@router.get("/workout-plans", response_model=List[WorkoutPlanRead])
async def get_workout_plans(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    workout_type: Optional[str] = None,
    is_completed: Optional[bool] = None
):
    """Récupère les plans d'entraînement de l'utilisateur"""
    user_id = get_current_user_id(token.credentials)
    
    query = select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
    
    if start_date:
        query = query.where(WorkoutPlan.planned_date >= start_date)
    if end_date:
        query = query.where(WorkoutPlan.planned_date <= end_date)
    if workout_type:
        query = query.where(WorkoutPlan.workout_type == workout_type)
    if is_completed is not None:
        query = query.where(WorkoutPlan.is_completed == is_completed)
    
    query = query.order_by(WorkoutPlan.planned_date.desc())
    
    plans = session.exec(query).all()
    return plans





@router.get("/workout-plans/{plan_id}", response_model=WorkoutPlanRead)
async def get_workout_plan(
    plan_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Récupère un plan d'entraînement spécifique"""
    user_id = get_current_user_id(token.credentials)
    
    plan = session.exec(
        select(WorkoutPlan).where(
            WorkoutPlan.id == plan_id,
            WorkoutPlan.user_id == UUID(user_id)
        )
    ).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout plan not found"
        )
    
    return plan


@router.patch("/workout-plans/{plan_id}", response_model=WorkoutPlanRead)
async def update_workout_plan(
    plan_id: UUID,
    plan_updates: WorkoutPlanUpdate,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Met à jour un plan d'entraînement"""
    user_id = get_current_user_id(token.credentials)
    
    plan = session.exec(
        select(WorkoutPlan).where(
            WorkoutPlan.id == plan_id,
            WorkoutPlan.user_id == UUID(user_id)
        )
    ).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout plan not found"
        )
    
    # Mettre à jour les champs
    for field, value in plan_updates.dict(exclude_unset=True).items():
        setattr(plan, field, value)
    
    plan.updated_at = datetime.utcnow()
    session.add(plan)
    session.commit()
    session.refresh(plan)
    
    return plan


@router.delete("/workout-plans/{plan_id}")
async def delete_workout_plan(
    plan_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime un plan d'entraînement"""
    user_id = get_current_user_id(token.credentials)
    
    plan = session.exec(
        select(WorkoutPlan).where(
            WorkoutPlan.id == plan_id,
            WorkoutPlan.user_id == UUID(user_id)
        )
    ).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout plan not found"
        )
    
    session.delete(plan)
    session.commit()
    
    return {"message": "Workout plan deleted successfully"}





# ============ SYNCHRONISATION ============

@router.post("/sync/strava")
async def sync_strava_activities(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    days_back: int = Query(default=30, ge=1, le=99999)
):
    """Synchronise les activités Strava de l'utilisateur"""
    user_id = get_current_user_id(token.credentials)
    
    try:
        result = strava_sync_service.sync_activities(session, user_id, days_back)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )


# ============ RGPD - SUPPRESSION DES DONNÉES ============

@router.delete("/data/strava")
async def delete_strava_data(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime toutes les données Strava de l'utilisateur (conformité RGPD)"""
    user_id = get_current_user_id(token.credentials)
    
    try:
        # Supprimer l'authentification Strava
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        
        if strava_auth:
            session.delete(strava_auth)
        
        # Supprimer toutes les activités avec strava_id (importées de Strava)
        strava_activities = session.exec(
            select(Activity).where(
                Activity.user_id == UUID(user_id),
                Activity.strava_id.is_not(None)
            )
        ).all()
        
        activities_count = len(strava_activities)
        for activity in strava_activities:
            session.delete(activity)
        
        session.commit()
        
        return {
            "message": "Données Strava supprimées avec succès",
            "deleted_activities": activities_count,
            "strava_auth_deleted": bool(strava_auth)
        }
        
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression des données Strava: {str(e)}"
        )


@router.delete("/data/all")
async def delete_all_user_data(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime toutes les données de l'utilisateur SAUF le compte (conformité RGPD)"""
    user_id = get_current_user_id(token.credentials)
    
    try:
        # Compter les données avant suppression
        activities_count = len(session.exec(
            select(Activity).where(Activity.user_id == UUID(user_id))
        ).all())
        
        workout_plans_count = len(session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all())
        
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        
        # Supprimer toutes les activités
        activities_to_delete = session.exec(
            select(Activity).where(Activity.user_id == UUID(user_id))
        ).all()
        for activity in activities_to_delete:
            session.delete(activity)
        
        # Supprimer tous les plans d'entraînement
        plans_to_delete = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()
        for plan in plans_to_delete:
            session.delete(plan)
        
        # Supprimer l'authentification Strava
        if strava_auth:
            session.delete(strava_auth)
        
        session.commit()
        
        return {
            "message": "Toutes les données utilisateur supprimées avec succès",
            "deleted_activities": activities_count,
            "deleted_workout_plans": workout_plans_count,
            "strava_auth_deleted": bool(strava_auth)
        }
        
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression des données: {str(e)}"
        )


@router.delete("/account")
async def delete_account(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Supprime complètement le compte utilisateur et toutes ses données (conformité RGPD)"""
    user_id = get_current_user_id(token.credentials)
    
    try:
        # Récupérer l'utilisateur
        user = session.get(User, UUID(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Compter les données avant suppression
        activities_count = len(session.exec(
            select(Activity).where(Activity.user_id == UUID(user_id))
        ).all())
        
        workout_plans_count = len(session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all())
        
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        
        # Supprimer toutes les données liées (l'ordre importe à cause des contraintes FK)
        # 1. Supprimer les activités
        activities_to_delete = session.exec(
            select(Activity).where(Activity.user_id == UUID(user_id))
        ).all()
        for activity in activities_to_delete:
            session.delete(activity)
        
        # 2. Supprimer les plans d'entraînement
        plans_to_delete = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()
        for plan in plans_to_delete:
            session.delete(plan)
        
        # 3. Supprimer l'authentification Strava
        if strava_auth:
            session.delete(strava_auth)
        
        # 4. Finalement, supprimer l'utilisateur
        session.delete(user)
        
        session.commit()
        
        return {
            "message": "Compte et toutes les données supprimés avec succès",
            "deleted_activities": activities_count,
            "deleted_workout_plans": workout_plans_count,
            "strava_auth_deleted": bool(strava_auth),
            "account_deleted": True
        }
        
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression du compte: {str(e)}"
        )


@router.get("/data/export")
async def export_user_data(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Exporte toutes les données de l'utilisateur au format JSON (conformité RGPD)"""
    import json
    
    user_id = get_current_user_id(token.credentials)
    
    try:
        # Récupérer l'utilisateur
        user = session.get(User, UUID(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Utilisateur non trouvé"
            )
        
        # Récupérer toutes les données
        activities = session.exec(
            select(Activity).where(Activity.user_id == UUID(user_id))
        ).all()
        
        workout_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()
        
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        
        # Préparer les données d'export (exclure les données sensibles)
        export_data = {
            "user": {
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
                "created_at": user.created_at.isoformat(),
                "is_active": user.is_active
            },
            "activities": [
                {
                    "id": str(activity.id),
                    "name": activity.name,
                    "activity_type": activity.activity_type,
                    "start_date": activity.start_date.isoformat(),
                    "distance": activity.distance,
                    "moving_time": activity.moving_time,
                    "elapsed_time": activity.elapsed_time,
                    "total_elevation_gain": activity.total_elevation_gain,
                    "average_speed": activity.average_speed,
                    "max_speed": activity.max_speed,
                    "average_heartrate": activity.average_heartrate,
                    "max_heartrate": activity.max_heartrate,
                    "average_cadence": activity.average_cadence,
                    "description": activity.description,
                    "strava_id": activity.strava_id,
                    "location_city": activity.location_city,
                    "location_country": activity.location_country,
                    "created_at": activity.created_at.isoformat()
                }
                for activity in activities
            ],
            "workout_plans": [
                {
                    "id": str(plan.id),
                    "name": plan.name,
                    "workout_type": plan.workout_type,
                    "planned_date": plan.planned_date.isoformat(),
                    "planned_distance": plan.planned_distance,
                    "planned_duration": plan.planned_duration,
                    "planned_pace": plan.planned_pace,
                    "planned_elevation_gain": plan.planned_elevation_gain,
                    "intensity_zone": plan.intensity_zone,
                    "description": plan.description,
                    "coach_notes": plan.coach_notes,
                    "is_completed": plan.is_completed,
                    "completion_percentage": plan.completion_percentage,
                    "created_at": plan.created_at.isoformat()
                }
                for plan in workout_plans
            ],
            "strava_connection": {
                "connected": bool(strava_auth),
                "athlete_id": strava_auth.strava_athlete_id if strava_auth else None,
                "scope": strava_auth.scope if strava_auth else None,
                "connected_at": strava_auth.created_at.isoformat() if strava_auth else None
            } if strava_auth else None,
            "export_date": datetime.utcnow().isoformat(),
            "export_type": "complete_user_data"
        }
        
        return JSONResponse(
            content=export_data,
            headers={
                "Content-Disposition": f"attachment; filename=athletiq_data_export_{user_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'export des données: {str(e)}"
        )


# ============ DONNÉES DÉTAILLÉES STRAVA ============

@router.get("/strava/quota")
async def get_strava_quota_status(
    token: str = Depends(security)
):
    """Récupère le statut des quotas API Strava"""
    # Vérifier l'authentification
    get_current_user_id(token.credentials)
    
    return detailed_strava_service.quota_manager.get_status()


# ============ IMPORT CSV ============

@router.post("/workout-plans/import-csv")
async def import_workout_plans_csv(
    file: UploadFile = File(...),
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Importe des plans d'entraînement depuis un fichier CSV"""
    user_id = get_current_user_id(token.credentials)
    
    # Vérifier le type de fichier
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le fichier doit être au format CSV"
        )
    
    try:
        # Lire le contenu du fichier
        content = await file.read()
        csv_content = content.decode('utf-8')
        
        # Parser le CSV
        plans = csv_import_service.parse_csv_content(csv_content, UUID(user_id))
        
        if not plans:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Aucun plan valide trouvé dans le fichier CSV"
            )
        
        # Importer dans la base de données
        result = csv_import_service.import_plans_to_database(session, plans, UUID(user_id))
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import: {str(e)}"
        )


@router.post("/activities/{activity_id}/enrich")
async def enrich_single_activity(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Enrichit une activité spécifique avec ses données détaillées Strava"""
    user_id = get_current_user_id(token.credentials)
    
    # Récupérer l'activité
    activity = session.exec(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == UUID(user_id)
        )
    ).first()
    
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activité non trouvée"
        )
    
    if not activity.strava_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cette activité n'est pas liée à Strava"
        )
    
    success = detailed_strava_service.enrich_activity_with_details(session, user_id, activity)
    
    if success:
        return {
            "message": "Activité enrichie avec succès",
            "activity_id": str(activity_id),
            "has_streams": bool(activity.streams_data),
            "has_laps": bool(activity.laps_data),
            "quota_status": detailed_strava_service.quota_manager.get_status()
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Échec de l'enrichissement de l'activité"
        )


# ============ ENRICHISSEMENT DÉTAILLÉ STRAVA ============

@router.post("/activities/enrich-batch")
async def enrich_batch_activities(
    token: str = Depends(security),
    session: Session = Depends(get_session),
    max_activities: int = Query(default=10, ge=1, le=50)
):
    """Exécute le script strava_activity_sync.py pour enrichir les activités"""
    import subprocess
    import os
    import logging
    import threading
    import time
    
    logger = logging.getLogger(__name__)
    user_id = get_current_user_id(token.credentials)
    
    try:
        # Vérifier que l'utilisateur a une connexion Strava
        strava_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == UUID(user_id))
        ).first()
        
        if not strava_auth:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Strava not connected"
            )
        
        # Chemin vers le script
        script_path = os.path.join(os.path.dirname(__file__), "..", "..", "strava_activity_sync.py")
        
        # Exécuter le script en arrière-plan
        logger.info(f"🚀 Démarrage enrichissement pour {max_activities} activités")
        
        # Utiliser subprocess pour exécuter le script avec des arguments
        process = subprocess.Popen(
            ["python", script_path, "--max-activities", str(max_activities)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.path.dirname(script_path)
        )
        
        # Attendre un peu pour voir si le script démarre correctement
        try:
            # Attendre 3 secondes maximum pour voir s'il y a une erreur immédiate
            stdout, stderr = process.communicate(timeout=3)
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else "Erreur inconnue"
                logger.error(f"❌ Erreur script enrichissement: {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Erreur lors de l'enrichissement: {error_msg}"
                )
            
            logger.info("✅ Script d'enrichissement terminé immédiatement")
            return {
                "message": f"Enrichissement terminé pour {max_activities} activités",
                "enriched_count": max_activities,  # Estimation
                "failed_count": 0,
                "quota_status": {
                    "daily_used": 0,
                    "daily_limit": 1000,
                    "per_15min_used": 0,
                    "per_15min_limit": 100,
                    "next_15min_reset": "",
                    "daily_reset": ""
                }
            }
            
        except subprocess.TimeoutExpired:
            # Le script continue de tourner en arrière-plan
            logger.info("⏳ Script d'enrichissement en cours d'exécution...")
            
            # Démarrer un thread pour surveiller le processus
            def monitor_process():
                try:
                    process.wait()
                    logger.info("✅ Script d'enrichissement terminé")
                except Exception as e:
                    logger.error(f"❌ Erreur surveillance script: {e}")
            
            monitor_thread = threading.Thread(target=monitor_process, daemon=True)
            monitor_thread.start()
            
            return {
                "message": f"Enrichissement démarré pour {max_activities} activités",
                "enriched_count": 0,
                "failed_count": 0,
                "quota_status": {
                    "daily_used": 0,
                    "daily_limit": 1000,
                    "per_15min_used": 0,
                    "per_15min_limit": 100,
                    "next_15min_reset": "",
                    "daily_reset": ""
                }
            }
            
    except Exception as e:
        logger.error(f"❌ Erreur lors du démarrage de l'enrichissement: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors du démarrage de l'enrichissement: {str(e)}"
        )


@router.get("/activities/{activity_id}/streams")
async def get_activity_streams(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Récupère les données détaillées (streams) d'une activité"""
    user_id = get_current_user_id(token.credentials)
    
    activity = session.exec(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == UUID(user_id)
        )
    ).first()
    
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activité non trouvée"
        )
    
    if not activity.streams_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Données détaillées non disponibles pour cette activité"
        )
    
    return {
        "activity_id": str(activity_id),
        "streams_data": activity.streams_data,
        "laps_data": activity.laps_data
    }


@router.post("/activities/auto-enrich/start")
async def start_auto_enrichment(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Démarre l'enrichissement automatique pour l'utilisateur"""
    user_id = get_current_user_id(token.credentials)
    
    # Ajouter les activités de l'utilisateur à la queue
    added_count = auto_enrichment_service.add_user_activities_to_queue(user_id)
    
    return {
        "message": f"Enrichissement automatique démarré",
        "activities_added_to_queue": added_count,
        "queue_status": auto_enrichment_service.get_queue_status()
    }


@router.post("/activities/{activity_id}/prioritize")
async def prioritize_activity_enrichment(
    activity_id: UUID,
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Met une activité en priorité haute pour l'enrichissement"""
    user_id = get_current_user_id(token.credentials)
    
    # Vérifier que l'activité appartient à l'utilisateur
    activity = session.exec(
        select(Activity).where(
            Activity.id == activity_id,
            Activity.user_id == UUID(user_id)
        )
    ).first()
    
    if not activity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Activité non trouvée"
        )
    
    if not activity.strava_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cette activité n'est pas liée à Strava"
        )
    
    if activity.streams_data:
        return {
            "message": "Cette activité est déjà enrichie",
            "activity_id": str(activity_id)
        }
    
    # Ajouter en priorité haute
    success = auto_enrichment_service.prioritize_activity(str(activity_id), user_id)
    
    if success:
        return {
            "message": "Activité ajoutée en priorité haute",
            "activity_id": str(activity_id),
            "queue_status": auto_enrichment_service.get_queue_status()
        }
    else:
        return {
            "message": "Activité déjà en queue",
            "activity_id": str(activity_id),
            "queue_status": auto_enrichment_service.get_queue_status()
        }


@router.get("/enrichment/queue-status")
async def get_enrichment_queue_status(
    token: str = Depends(security)
):
    """Récupère le statut de la queue d'enrichissement"""
    # Vérifier l'authentification
    get_current_user_id(token.credentials)
    
    return auto_enrichment_service.get_queue_status()


# ============ GOOGLE CALENDAR SIMPLIFIÉ ============

@router.get("/google-calendar/calendars")
async def get_google_calendars(
    session: Session = Depends(get_session),
    token_credentials: str = Depends(security)
):
    try:
        # Extraire le token JWT et récupérer l'utilisateur
        token = extract_token_from_credentials(token_credentials)
        user_id = get_current_user_id(token)
        
        # Récupérer les tokens Google de l'utilisateur
        google_auth = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()
        
        if not google_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Utilisateur non connecté à Google Calendar"
            )
        
        # Vérifier si le token a expiré et le rafraîchir si nécessaire
        from app.auth.google_oauth import google_oauth
        is_expired = google_auth.expires_at < datetime.now() if google_auth.expires_at else True
        
        if is_expired:
            logger.info("Token Google expiré, rafraîchissement automatique...")
            try:
                # Déchiffrer le refresh token
                refresh_token = google_oauth.decrypt_token(google_auth.refresh_token_encrypted)
                
                # Rafraîchir le token
                new_tokens = google_oauth.refresh_access_token(refresh_token)
                
                # Chiffrer et sauvegarder les nouveaux tokens
                encrypted_access_token = google_oauth.encrypt_token(new_tokens.access_token)
                encrypted_refresh_token = google_oauth.encrypt_token(new_tokens.refresh_token)
                
                # Mettre à jour en base de données
                google_auth.access_token_encrypted = encrypted_access_token
                google_auth.refresh_token_encrypted = encrypted_refresh_token
                google_auth.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
                google_auth.updated_at = datetime.now()
                
                session.add(google_auth)
                session.commit()
                
                logger.info("Token Google rafraîchi avec succès")
                
            except Exception as refresh_error:
                logger.error(f"Erreur lors du refresh automatique: {refresh_error}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token Google expiré et impossible à rafraîchir. Veuillez vous reconnecter."
                )
        
        # Déchiffrer le token d'accès (maintenant valide)
        decrypted_token = google_oauth.decrypt_token(google_auth.access_token_encrypted)
        
        # Récupérer les calendriers avec le token d'authentification
        calendars = google_calendar_service.get_user_calendars(decrypted_token)
        return {"calendars": calendars}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la récupération des calendriers: {str(e)}"
        )


@router.post("/google-calendar/export")
async def export_workout_plans_to_google(
    calendar_id: str = Form("primary"),
    session: Session = Depends(get_session),
    token_credentials: str = Depends(security)
):
    """Exporte les plans d'entraînement vers Google Calendar"""
    try:
        # Extraire le token JWT et récupérer l'utilisateur
        token = extract_token_from_credentials(token_credentials)
        user_id = get_current_user_id(token)
        
        # Récupérer et vérifier les tokens Google de l'utilisateur
        google_auth = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()
        
        if not google_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Utilisateur non connecté à Google Calendar"
            )
        
        # Vérifier si le token a expiré et le rafraîchir si nécessaire
        from app.auth.google_oauth import google_oauth
        is_expired = google_auth.expires_at < datetime.now() if google_auth.expires_at else True
        
        if is_expired:
            logger.info("Token Google expiré, rafraîchissement automatique...")
            try:
                # Déchiffrer le refresh token
                refresh_token = google_oauth.decrypt_token(google_auth.refresh_token_encrypted)
                
                # Rafraîchir le token
                new_tokens = google_oauth.refresh_access_token(refresh_token)
                
                # Chiffrer et sauvegarder les nouveaux tokens
                encrypted_access_token = google_oauth.encrypt_token(new_tokens.access_token)
                encrypted_refresh_token = google_oauth.encrypt_token(new_tokens.refresh_token)
                
                # Mettre à jour en base de données
                google_auth.access_token_encrypted = encrypted_access_token
                google_auth.refresh_token_encrypted = encrypted_refresh_token
                google_auth.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
                google_auth.updated_at = datetime.now()
                
                session.add(google_auth)
                session.commit()
                
                logger.info("Token Google rafraîchi avec succès")
                
            except Exception as refresh_error:
                logger.error(f"Erreur lors du refresh automatique: {refresh_error}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token Google expiré et impossible à rafraîchir. Veuillez vous reconnecter."
                )
        
        # Déchiffrer le token d'accès (maintenant valide)
        decrypted_token = google_oauth.decrypt_token(google_auth.access_token_encrypted)
        
        # Récupérer les plans d'entraînement de l'utilisateur
        workout_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()
        
        if not workout_plans:
            return {
                "success": True,
                "message": "Aucun plan d'entraînement à exporter",
                "exported_count": 0,
                "total_count": 0
            }
        
        # Convertir en format dict pour le service
        plans_data = []
        for plan in workout_plans:
            plans_data.append({
                "workout_type": plan.workout_type,
                "description": plan.description or "",
                "planned_date": plan.planned_date.isoformat(),
                "duration_minutes": plan.planned_duration // 60 if plan.planned_duration else 60
            })
        
        result = google_calendar_service.export_workout_plans_to_google(
            plans_data, calendar_id, decrypted_token
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'export: {str(e)}"
        )


@router.post("/google-calendar/import")
async def import_google_calendar_as_workout_plans(
    calendar_id: str = Form("primary"),
    start_date: Optional[str] = Form(None),
    end_date: Optional[str] = Form(None),
    session: Session = Depends(get_session),
    token_credentials: str = Depends(security)
):
    """Importe les événements Google Calendar comme plans d'entraînement"""
    try:
        # Extraire le token JWT et récupérer l'utilisateur
        token = extract_token_from_credentials(token_credentials)
        user_id = get_current_user_id(token)
        
        # Récupérer et vérifier les tokens Google de l'utilisateur
        google_auth = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()
        
        if not google_auth:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Utilisateur non connecté à Google Calendar"
            )
        
        # Vérifier si le token a expiré et le rafraîchir si nécessaire
        from app.auth.google_oauth import google_oauth
        is_expired = google_auth.expires_at < datetime.now() if google_auth.expires_at else True
        
        if is_expired:
            logger.info("Token Google expiré, rafraîchissement automatique...")
            try:
                # Déchiffrer le refresh token
                refresh_token = google_oauth.decrypt_token(google_auth.refresh_token_encrypted)
                
                # Rafraîchir le token
                new_tokens = google_oauth.refresh_access_token(refresh_token)
                
                # Chiffrer et sauvegarder les nouveaux tokens
                encrypted_access_token = google_oauth.encrypt_token(new_tokens.access_token)
                encrypted_refresh_token = google_oauth.encrypt_token(new_tokens.refresh_token)
                
                # Mettre à jour en base de données
                google_auth.access_token_encrypted = encrypted_access_token
                google_auth.refresh_token_encrypted = encrypted_refresh_token
                google_auth.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
                google_auth.updated_at = datetime.now()
                
                session.add(google_auth)
                session.commit()
                
                logger.info("Token Google rafraîchi avec succès")
                
            except Exception as refresh_error:
                logger.error(f"Erreur lors du refresh automatique: {refresh_error}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token Google expiré et impossible à rafraîchir. Veuillez vous reconnecter."
                )
        
        # Déchiffrer le token d'accès (maintenant valide)
        decrypted_token = google_oauth.decrypt_token(google_auth.access_token_encrypted)
        
        # Importer depuis Google Calendar
        imported_plans = google_calendar_service.import_google_calendar_as_workout_plans(
            calendar_id, start_date, end_date, decrypted_token
        )
        
        # Synchronisation complète avec Google Calendar
        saved_count = 0
        updated_count = 0
        deleted_count = 0
        
        logger.info(f"Synchronisation avec {len(imported_plans)} événements Google Calendar")
        
        # Récupérer tous les plans existants pour cet utilisateur
        existing_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == UUID(user_id))
        ).all()
        
        # Créer un dictionnaire des plans existants par date et nom
        existing_plans_dict = {}
        for plan in existing_plans:
            key = (plan.planned_date, plan.name)
            existing_plans_dict[key] = plan
        
        # Traiter chaque événement Google Calendar
        for plan_data in imported_plans:
            try:
                event_name = plan_data.get('summary', 'Sans titre')
                event_date = datetime.fromisoformat(plan_data["planned_date"]).date()
                key = (event_date, event_name)
                
                logger.info(f"Traitement de l'événement: {event_name} du {event_date}")
                
                # Vérifier si le plan existe déjà
                existing_plan = existing_plans_dict.get(key)
                
                if not existing_plan:
                    try:
                        # Créer le nouveau plan avec les données Google Calendar
                        workout_plan = WorkoutPlan(
                            user_id=UUID(user_id),
                            name=plan_data.get("summary", f"Entraînement - {datetime.fromisoformat(plan_data['planned_date']).strftime('%d/%m/%Y')}"),  # Titre de l'événement
                            workout_type=WorkoutType.EASY_RUN,  # Utiliser l'enum directement
                            planned_date=datetime.fromisoformat(plan_data["planned_date"]).date(),
                            planned_distance=0.0,  # À remplir manuellement
                            planned_duration=plan_data.get("duration_minutes", 60) * 60,  # Durée de l'événement
                            planned_pace=0.0,  # À remplir manuellement
                            planned_elevation_gain=0.0,  # À remplir manuellement
                            description=plan_data.get("description", ""),  # Description de l'événement
                            coach_notes=plan_data.get("description", ""),  # Description comme notes du coach
                            is_completed=False
                        )
                    except Exception as e:
                        logger.error(f"Erreur lors de la création du plan {plan_data.get('summary', 'Sans titre')}: {e}")
                        continue
                    session.add(workout_plan)
                    saved_count += 1
                    logger.info(f"Plan créé: {workout_plan.name}")
                else:
                    # Mettre à jour le plan existant
                    existing_plan.description = plan_data.get("description", "")
                    existing_plan.coach_notes = plan_data.get("description", "")
                    existing_plan.planned_duration = plan_data.get("duration_minutes", 60) * 60
                    updated_count += 1
                    logger.info(f"Plan mis à jour: {existing_plan.name}")
                
                # Marquer ce plan comme traité
                existing_plans_dict.pop(key, None)
                    
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde du plan: {e}")
                continue
        
        # Supprimer les plans qui n'existent plus dans Google Calendar
        for key, plan in existing_plans_dict.items():
            try:
                logger.info(f"Suppression du plan: {plan.name} (plus dans Google Calendar)")
                session.delete(plan)
                deleted_count += 1
            except Exception as e:
                logger.error(f"Erreur lors de la suppression du plan: {e}")
                continue
        
        # Récupérer les informations de l'utilisateur pour le fichier JSON
        user = session.exec(
            select(User).where(User.id == UUID(user_id))
        ).first()
        
        # Créer le fichier JSON avec le format demandé
        import json
        import os
        
        # Créer le dossier data s'il n'existe pas
        data_dir = os.path.join(os.getcwd(), 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        # Créer le nom du fichier avec timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"imported_calendar_{timestamp}.json"
        filepath = os.path.join(data_dir, filename)
        
        # Préparer les données pour le fichier JSON
        json_data = {
            "import_info": {
                "import_date": datetime.now().isoformat(),
                "calendar_id": calendar_id,
                "time_range": {
                    "start_date": start_date,
                    "end_date": end_date
                },
                "total_events_imported": len(imported_plans)
            },
            "imported_events": [
                {
                    "summary": plan_data.get('summary', 'Sans titre'),
                    "description": plan_data.get('description', ''),
                    "planned_date": plan_data.get('planned_date'),
                    "duration_minutes": plan_data.get('duration_minutes', 60),
                    "is_completed": False,
                    "source": "google_calendar"
                }
                for plan_data in imported_plans
            ],
            "user_info": {
                "user_id": str(user_id),
                "email": user.email if user else "unknown",
                "full_name": user.full_name if user else "unknown"
            }
        }
        
        # Écrire le fichier JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Fichier JSON créé: {filepath}")
        
        session.commit()
        
        return {
            "success": True,
            "imported_count": saved_count,
            "updated_count": updated_count,
            "deleted_count": deleted_count,
            "total_found": len(imported_plans),
            "json_file_created": filename,
            "message": f"Synchronisation terminée: {saved_count} créés, {updated_count} mis à jour, {deleted_count} supprimés. Fichier JSON créé: {filename}"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de l'import: {str(e)}"
        )







