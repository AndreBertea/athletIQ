"""
Utilitaires partages entre les routers API.
"""
import logging
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from jose import JWTError, jwt as jose_jwt

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def security(request: Request) -> HTTPAuthorizationCredentials:
    """Extrait le JWT depuis le header Bearer ou le cookie access_token."""
    # 1. Essayer le header Authorization: Bearer <token>
    creds = await _bearer_scheme(request)
    if creds:
        return creds

    # 2. Fallback sur le cookie httpOnly
    token = request.cookies.get("access_token")
    if token:
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token_from_request(request: Request) -> str | None:
    """Extrait le JWT brut depuis header ou cookie (pour le rate limiter)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("access_token")


def _get_user_or_ip(request: Request) -> str:
    """Key function pour le rate limiter : retourne le user_id JWT si present, sinon l'IP."""
    token = _extract_token_from_request(request)
    if token:
        try:
            from app.core.settings import get_settings
            settings = get_settings()
            payload = jose_jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except JWTError:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=_get_user_or_ip, default_limits=["100/minute"], headers_enabled=True)


def extract_token_from_credentials(token_credentials) -> str:
    """Extrait le token de l'objet credentials"""
    if hasattr(token_credentials, 'credentials'):
        return token_credentials.credentials
    return str(token_credentials)


def set_auth_cookies(response: JSONResponse, access_token: str, refresh_token: str) -> JSONResponse:
    """Pose les cookies httpOnly pour access_token et refresh_token."""
    from app.core.settings import get_settings
    settings = get_settings()
    is_prod = settings.ENVIRONMENT == "production"
    # Cross-site (frontend/backend sur des domaines differents) => SameSite=None + Secure
    samesite_value = "none" if is_prod else "lax"

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_prod,
        samesite=samesite_value,
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_prod,
        samesite=samesite_value,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/",
    )
    return response


def clear_auth_cookies(response: JSONResponse) -> JSONResponse:
    """Supprime les cookies d'authentification."""
    from app.core.settings import get_settings
    settings = get_settings()
    is_prod = settings.ENVIRONMENT == "production"
    samesite_value = "none" if is_prod else "lax"

    response.delete_cookie(key="access_token", path="/", httponly=True, secure=is_prod, samesite=samesite_value)
    response.delete_cookie(key="refresh_token", path="/", httponly=True, secure=is_prod, samesite=samesite_value)
    return response
