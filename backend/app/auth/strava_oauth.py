"""
Gestion de l'authentification OAuth Strava
"""
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.core.settings import get_settings

settings = get_settings()


class StravaTokens(BaseModel):
    """Tokens Strava reçus de l'API"""
    access_token: str
    refresh_token: str
    expires_at: int
    scope: str
    athlete_id: int


class StravaAthleteInfo(BaseModel):
    """Informations de l'athlète Strava"""
    id: int
    firstname: str
    lastname: str
    city: Optional[str] = None
    country: Optional[str] = None
    profile: Optional[str] = None


class StravaOAuthManager:
    """Gestionnaire OAuth Strava"""
    
    def __init__(self):
        import logging
        logger = logging.getLogger(__name__)
        
        self.client_id = settings.STRAVA_CLIENT_ID
        self.client_secret = settings.STRAVA_CLIENT_SECRET
        self.redirect_uri = settings.STRAVA_REDIRECT_URI
        self.base_url = "https://www.strava.com"
        self.api_url = "https://www.strava.com/api/v3"
        
        # Validation de la configuration OAuth
        if not self.client_id:
            logger.error("STRAVA_CLIENT_ID manquant dans la configuration")
            
        if not self.client_secret:
            logger.error("STRAVA_CLIENT_SECRET manquant dans la configuration")
            
        if not self.redirect_uri:
            logger.error("STRAVA_REDIRECT_URI manquant dans la configuration")
        
        logger.info(f"Configuration OAuth Strava:")
        logger.info(f"  - Client ID: {self.client_id}")
        logger.info(f"  - Client Secret: {'✓ configuré' if self.client_secret else '✗ manquant'}")
        logger.info(f"  - Redirect URI: {self.redirect_uri}")
        
        # Encryption pour les tokens stockés
        self.encryption_key = settings.ENCRYPTION_KEY
        if self.encryption_key:
            try:
                self.cipher = Fernet(self.encryption_key.encode())
                logger.info("  - Encryption: ✓ configuré")
            except Exception as e:
                logger.error(f"  - Encryption: ✗ erreur - {e}")
                self.cipher = None
        else:
            logger.error("  - Encryption: ✗ ENCRYPTION_KEY manquante")
            self.cipher = None
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Génère l'URL d'autorisation Strava
        
        Args:
            state: Paramètre d'état optionnel pour la sécurité
            
        Returns:
            URL d'autorisation Strava
        """
        base_auth_url = f"{self.base_url}/oauth/authorize"
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "read,activity:read_all",  # Permissions demandées
            "approval_prompt": "auto"
        }
        
        if state:
            params["state"] = state
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_auth_url}?{query_string}"
    
    def exchange_code_for_tokens(self, code: str) -> StravaTokens:
        """
        Échange le code d'autorisation contre les tokens d'accès
        
        Args:
            code: Code d'autorisation reçu du callback Strava
            
        Returns:
            Tokens Strava avec informations de l'athlète
        """
        import logging
        logger = logging.getLogger(__name__)
        
        token_url = f"{self.api_url}/oauth/token"  # Correction : utiliser l'endpoint API v3
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code"
        }
        
        logger.info(f"Échange de code avec Strava API: {token_url}")
        logger.info(f"Client ID: {self.client_id}")
        logger.info(f"Code: {code[:10]}..." if code else "Code vide")
        
        try:
            response = requests.post(token_url, data=data, timeout=30)
            logger.info(f"Réponse Strava status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Erreur Strava API: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Strava API error {response.status_code}: {response.text}"
                )
            
            response.raise_for_status()
            
            token_data = response.json()
            logger.info(f"Token data reçu: athlete_id={token_data.get('athlete', {}).get('id')}")
            
            # Vérifier que tous les champs requis sont présents
            required_fields = ["access_token", "refresh_token", "expires_at", "athlete"]  # 'scope' peut être absent selon Strava
            missing_fields = [field for field in required_fields if field not in token_data]
            if missing_fields:
                logger.error(f"Champs manquants dans la réponse Strava: {missing_fields}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid Strava response: missing fields {missing_fields}"
                )
            
            if "id" not in token_data["athlete"]:
                logger.error("ID athlète manquant dans la réponse Strava")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Strava response: missing athlete ID"
                )
            
            scope_value = token_data.get("scope", "read")  # Valeur par défaut si absent

            return StravaTokens(
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
                scope=scope_value,
                athlete_id=token_data["athlete"]["id"]
            )
            
        except requests.RequestException as e:
            logger.error(f"Erreur réseau lors de l'échange de tokens: {type(e).__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Network error during token exchange: {type(e).__name__}: {str(e)}"
            )
        except KeyError as e:
            logger.error(f"Erreur de structure de données Strava: {str(e)}")
            logger.error(f"Réponse complète: {token_data if 'token_data' in locals() else 'N/A'}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid Strava response structure: missing key {str(e)}"
            )
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'échange de tokens: {type(e).__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Unexpected error during token exchange: {type(e).__name__}: {str(e)}"
            )
    
    def refresh_access_token(self, refresh_token_encrypted: str) -> StravaTokens:
        """
        Actualise l'access token avec le refresh token
        
        Args:
            refresh_token_encrypted: Refresh token chiffré
            
        Returns:
            Nouveaux tokens Strava
        """
        # Déchiffrer le refresh token
        refresh_token = self.decrypt_token(refresh_token_encrypted)
        
        token_url = f"{self.api_url}/oauth/token"  # Correction : utiliser l'endpoint API v3
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            response = requests.post(token_url, data=data, timeout=30)
            response.raise_for_status()
            
            token_data = response.json()
            
            return StravaTokens(
                access_token=token_data["access_token"],
                refresh_token=token_data["refresh_token"],
                expires_at=token_data["expires_at"],
                scope=token_data.get("scope", "read,activity:read_all"),
                athlete_id=0  # L'ID athlète n'est pas retourné lors du refresh
            )
            
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to refresh access token: {str(e)}"
            )
    
    def get_athlete_info(self, access_token: str) -> StravaAthleteInfo:
        """
        Récupère les informations de l'athlète
        
        Args:
            access_token: Token d'accès Strava
            
        Returns:
            Informations de l'athlète
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            response = requests.get(
                f"{self.api_url}/athlete",
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            
            athlete_data = response.json()
            
            return StravaAthleteInfo(
                id=athlete_data["id"],
                firstname=athlete_data.get("firstname", ""),
                lastname=athlete_data.get("lastname", ""),
                city=athlete_data.get("city"),
                country=athlete_data.get("country"),
                profile=athlete_data.get("profile")
            )
            
        except requests.RequestException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to get athlete info: {str(e)}"
            )
    
    def is_token_expired(self, expires_at: datetime) -> bool:
        """
        Vérifie si un token est expiré
        
        Args:
            expires_at: Date d'expiration du token
            
        Returns:
            True si le token est expiré
        """
        # Ajouter une marge de 5 minutes pour éviter les erreurs de timing
        return datetime.utcnow() + timedelta(minutes=5) >= expires_at
    
    def encrypt_token(self, token: str) -> str:
        """
        Chiffre un token pour le stockage
        
        Args:
            token: Token à chiffrer
            
        Returns:
            Token chiffré en base64
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.cipher:
            logger.error("Cipher non configuré - ENCRYPTION_KEY manquante")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Encryption not configured: ENCRYPTION_KEY missing"
            )
        
        if not token:
            logger.error("Token vide fourni pour le chiffrement")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty token provided for encryption"
            )
        
        try:
            encrypted = self.cipher.encrypt(token.encode())
            logger.info("Token chiffré avec succès")
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Erreur lors du chiffrement du token: {type(e).__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to encrypt token: {type(e).__name__}: {str(e)}"
            )
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Déchiffre un token stocké
        
        Args:
            encrypted_token: Token chiffré
            
        Returns:
            Token en clair
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self.cipher:
            logger.error("Cipher non configuré - ENCRYPTION_KEY manquante")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Encryption not configured: ENCRYPTION_KEY missing"
            )
        
        if not encrypted_token:
            logger.error("Token chiffré vide fourni pour le déchiffrement")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty encrypted token provided for decryption"
            )
        
        try:
            decrypted = self.cipher.decrypt(encrypted_token.encode())
            logger.info("Token déchiffré avec succès")
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Erreur lors du déchiffrement du token: {type(e).__name__}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to decrypt token: {type(e).__name__}: {str(e)}"
            )
    
    def validate_scope(self, scope: str, required_scopes: list = None) -> bool:
        """
        Valide que les permissions accordées sont suffisantes
        
        Args:
            scope: Scope accordé par Strava
            required_scopes: Permissions requises
            
        Returns:
            True si les permissions sont suffisantes
        """
        if required_scopes is None:
            required_scopes = ["read", "activity:read_all"]
        
        granted_scopes = scope.split(",")
        return all(req in granted_scopes for req in required_scopes)


# Instance globale
strava_oauth = StravaOAuthManager()


def generate_encryption_key() -> str:
    """Génère une clé de chiffrement pour les tokens Strava"""
    return Fernet.generate_key().decode() 