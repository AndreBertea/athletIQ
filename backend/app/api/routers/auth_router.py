"""
Routes d'authentification : signup, login, me, OAuth Strava, OAuth Google.
Routes = validation + delegation au service. Pas de logique metier ici.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Form
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session

from app.core.database import get_session
from app.core.settings import get_settings
from app.auth.jwt import TokenResponse, jwt_manager, get_current_user_id
from app.auth.strava_oauth import strava_oauth
from app.auth.google_oauth import google_oauth
from app.domain.entities import UserCreate, UserRead
from app.domain.services.auth_service import auth_service
from app.api.routers._shared import security, limiter, set_auth_cookies, clear_auth_cookies

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ GOOGLE OAUTH ============

@router.get("/auth/google/login")
async def google_login():
    """Redirige vers l'autorisation Google OAuth"""
    try:
        auth_url = google_oauth.get_authorization_url()
        return {"auth_url": auth_url}
    except Exception as e:
        logger.error(f"Erreur lors de la generation de l'URL d'autorisation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la generation de l'URL d'autorisation: {str(e)}"
        )


@router.get("/auth/google/status")
async def google_status(
    token_credentials: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Verifie le statut de la connexion Google OAuth"""
    try:
        token = token_credentials.credentials if hasattr(token_credentials, 'credentials') else str(token_credentials)
        user_id = get_current_user_id(token)
        return auth_service.get_google_status(session, user_id)
    except Exception as e:
        logger.error(f"Erreur lors de la verification du statut Google: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la verification du statut Google"
        )


@router.post("/auth/google/refresh")
async def google_refresh_token(
    token_credentials: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Rafraichit automatiquement le token Google OAuth"""
    try:
        token = token_credentials.credentials if hasattr(token_credentials, 'credentials') else str(token_credentials)
        user_id = get_current_user_id(token)
        return auth_service.refresh_google_token(session, user_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
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
    """Callback Google OAuth - echange le code contre des tokens"""
    try:
        user, jwt_tokens, google_user_id = auth_service.handle_google_callback(session, code)

        settings = get_settings()
        response = RedirectResponse(
            url=f"{settings.FRONTEND_URL}/google-connect?success=true&google_user_id={google_user_id}"
        )
        set_auth_cookies(response, jwt_tokens.access_token, jwt_tokens.refresh_token)
        return response

    except Exception as e:
        logger.error(f"Erreur lors de l'authentification Google: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erreur lors de l'authentification Google: {str(e)}"
        )


# ============ AUTH LOCALE ============

@router.post("/auth/signup")
@limiter.limit("3/hour")
async def signup(
    request: Request,
    user_data: UserCreate,
    session: Session = Depends(get_session)
):
    """Inscription d'un nouvel utilisateur"""
    try:
        tokens = auth_service.signup(session, user_data)
        response = JSONResponse(content=tokens.model_dump())
        return set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    """Connexion utilisateur"""
    try:
        tokens = auth_service.login(session, email, password)
        response = JSONResponse(content=tokens.model_dump())
        return set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    except ValueError as e:
        error_msg = str(e)
        if "Inactive" in error_msg:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=error_msg)


@router.post("/auth/refresh")
async def refresh_token(request: Request):
    """Rafraichit l'access token a partir du refresh token (cookie ou body JSON)."""
    # Lire le refresh token depuis le cookie ou le body
    refresh_tok = request.cookies.get("refresh_token")
    if not refresh_tok:
        try:
            body = await request.json()
            refresh_tok = body.get("refresh_token")
        except Exception:
            pass
    if not refresh_tok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    try:
        new_access = jwt_manager.refresh_access_token(refresh_tok)
        response = JSONResponse(content={"access_token": new_access})
        # Mettre a jour le cookie access_token
        from app.core.settings import get_settings
        settings = get_settings()
        is_prod = settings.ENVIRONMENT == "production"
        response.set_cookie(
            key="access_token",
            value=new_access,
            httponly=True,
            secure=is_prod,
            samesite="lax",
            max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur refresh token: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")


@router.post("/auth/logout")
async def logout():
    """Supprime les cookies d'authentification."""
    response = JSONResponse(content={"message": "Logged out"})
    return clear_auth_cookies(response)


@router.get("/auth/me", response_model=UserRead)
async def get_current_user(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Recupere les informations de l'utilisateur connecte"""
    user_id = get_current_user_id(token.credentials)
    try:
        return auth_service.get_user(session, user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


# ============ OAUTH STRAVA ============

@router.get("/auth/strava/login")
async def strava_login(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Initie la connexion OAuth Strava"""
    user_id = get_current_user_id(token.credentials)
    auth_url = strava_oauth.get_authorization_url(state=user_id)
    return {"authorization_url": auth_url}


@router.get("/auth/strava/callback")
async def strava_callback(
    request: Request,
    session: Session = Depends(get_session)
):
    """Callback OAuth Strava - Traite l'authentification et redirige"""
    params = dict(request.query_params)
    code = params.get("code")
    state = params.get("state")
    error = params.get("error")

    settings = get_settings()

    if error:
        logger.error(f"Erreur OAuth recue de Strava: {error}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?error=oauth_error&message={error}")

    if not code:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?error=no_code&message=Code d'autorisation manquant")

    if not state:
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?error=no_state&message=Parametre d'etat manquant")

    try:
        (athlete_id,) = auth_service.handle_strava_callback(session, code, state)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?success=true&athlete_id={athlete_id}")

    except ValueError as e:
        error_msg = str(e)
        if "invalide" in error_msg.lower():
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?error=invalid_state&message={error_msg}")
        if "non trouve" in error_msg.lower():
            return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?error=user_not_found&message={error_msg}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?error=callback_error&message={error_msg}")

    except Exception as e:
        logger.error(f"Erreur dans le callback Strava: {type(e).__name__}: {str(e)}", exc_info=True)
        error_msg = f"{type(e).__name__}: {str(e)}"
        error_msg_encoded = error_msg.replace(" ", "%20").replace(":", "%3A")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/strava-connect?error=callback_error&message={error_msg_encoded}")


@router.get("/auth/strava/status")
async def strava_status(
    token: str = Depends(security),
    session: Session = Depends(get_session)
):
    """Verifie le statut de connexion Strava"""
    user_id = get_current_user_id(token.credentials)
    return auth_service.get_strava_status(session, user_id)
