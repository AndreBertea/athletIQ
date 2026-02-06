"""
Gestion de l'authentification OAuth Google Calendar
"""
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.core.settings import get_settings

settings = get_settings()


class GoogleTokens(BaseModel):
    """Tokens Google reçus de l'API"""
    access_token: str
    refresh_token: str
    expires_at: int
    scope: str
    google_user_id: str


class GoogleOAuthManager:
    """Gestionnaire OAuth Google Calendar"""
    
    def __init__(self):
        import logging
        logger = logging.getLogger(__name__)
        
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
        self.base_url = "https://accounts.google.com"
        self.api_url = "https://www.googleapis.com"
        
        # Validation de la configuration OAuth
        if not self.client_id:
            logger.error("GOOGLE_CLIENT_ID manquant dans la configuration")
            
        if not self.client_secret:
            logger.error("GOOGLE_CLIENT_SECRET manquant dans la configuration")
            
        if not self.redirect_uri:
            logger.error("GOOGLE_REDIRECT_URI manquant dans la configuration")
        
        logger.info(f"Configuration OAuth Google:")
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
        Génère l'URL d'autorisation Google
        
        Args:
            state: Paramètre d'état optionnel pour la sécurité
            
        Returns:
            URL d'autorisation Google
        """
        base_auth_url = f"{self.base_url}/o/oauth2/v2/auth"
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile",
            "access_type": "offline",
            "prompt": "consent"
        }
        
        if state:
            params["state"] = state
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{base_auth_url}?{query_string}"
    
    def exchange_code_for_tokens(self, code: str) -> GoogleTokens:
        """
        Échange le code d'autorisation contre les tokens d'accès
        
        Args:
            code: Code d'autorisation reçu du callback Google
            
        Returns:
            Tokens Google avec informations de l'utilisateur
        """
        import logging
        logger = logging.getLogger(__name__)
        
        token_url = "https://oauth2.googleapis.com/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }
        
        try:
            logger.info("Échange du code contre les tokens Google...")
            logger.info(f"URL: {token_url}")
            logger.info(f"Data: {data}")
            response = requests.post(token_url, data=data)
            
            if not response.ok:
                logger.error(f"Erreur HTTP {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Erreur Google OAuth: {response.status_code} - {response.text}"
                )
            
            response.raise_for_status()
            token_data = response.json()
            logger.info("Tokens Google reçus avec succès")
            logger.info(f"Token data: {token_data}")
            
            # Récupérer les informations de l'utilisateur
            user_info = self.get_user_info(token_data["access_token"])
            
            return GoogleTokens(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token", ""),
                expires_at=int(datetime.utcnow().timestamp()) + token_data.get("expires_in", 3600),
                scope=token_data.get("scope", ""),
                google_user_id=user_info["id"]
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de l'échange de tokens: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Erreur lors de l'authentification Google"
            )
    
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Récupère les informations de l'utilisateur Google
        
        Args:
            access_token: Token d'accès Google
            
        Returns:
            Informations de l'utilisateur
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            response = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors de la récupération des infos utilisateur: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Erreur lors de la récupération des informations utilisateur"
            )
    
    def refresh_access_token(self, refresh_token: str) -> GoogleTokens:
        """
        Actualise un token d'accès expiré
        
        Args:
            refresh_token: Token de rafraîchissement
            
        Returns:
            Nouveaux tokens Google
        """
        import logging
        logger = logging.getLogger(__name__)
        
        token_url = "https://oauth2.googleapis.com/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            logger.info("Actualisation du token Google...")
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            token_data = response.json()
            logger.info("Token Google actualisé avec succès")
            
            return GoogleTokens(
                access_token=token_data["access_token"],
                refresh_token=refresh_token,  # Garder l'ancien refresh token
                expires_at=int(datetime.utcnow().timestamp()) + token_data.get("expires_in", 3600),
                scope=token_data.get("scope", ""),
                google_user_id=""  # Pas de changement d'utilisateur
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de l'actualisation du token: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Erreur lors de l'actualisation du token Google"
            )
    
    def is_token_expired(self, expires_at: datetime) -> bool:
        """
        Vérifie si un token est expiré
        
        Args:
            expires_at: Date d'expiration du token
            
        Returns:
            True si le token est expiré
        """
        return datetime.utcnow() >= expires_at
    
    def encrypt_token(self, token: str) -> str:
        """
        Chiffre un token pour le stockage
        
        Args:
            token: Token à chiffrer
            
        Returns:
            Token chiffré
        """
        if not self.cipher:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Encryption non configurée"
            )
        
        return self.cipher.encrypt(token.encode()).decode()
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """
        Déchiffre un token stocké
        
        Args:
            encrypted_token: Token chiffré
            
        Returns:
            Token déchiffré
        """
        if not self.cipher:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Encryption non configurée"
            )
        
        try:
            return self.cipher.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Erreur lors du déchiffrement du token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors du déchiffrement du token"
            )


# Instance globale du gestionnaire OAuth Google
google_oauth = GoogleOAuthManager() 