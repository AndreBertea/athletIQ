"""
Gestion de l'authentification Garmin Connect via Garth
Email et mot de passe ne sont JAMAIS stockes — login one-time, token Garth chiffre.
"""
import logging
from cryptography.fernet import Fernet
from fastapi import HTTPException, status

import garth

from app.core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class GarminAuthManager:
    """Gestionnaire d'authentification Garmin Connect"""

    def __init__(self):
        self.encryption_key = settings.ENCRYPTION_KEY
        if self.encryption_key:
            try:
                self.cipher = Fernet(self.encryption_key.encode())
            except Exception as e:
                logger.error(f"Erreur initialisation Fernet: {e}")
                self.cipher = None
        else:
            logger.error("ENCRYPTION_KEY manquante")
            self.cipher = None

    def login(self, email: str, password: str) -> str:
        """
        Authentification Garmin via Garth.
        Retourne le token Garth serialise et chiffre.
        Email et mot de passe ne sont PAS stockes.

        Args:
            email: Email du compte Garmin
            password: Mot de passe du compte Garmin

        Returns:
            Token Garth chiffre (string)

        Raises:
            HTTPException 401 si login echoue
            HTTPException 500 si erreur interne
        """
        client = garth.Client(domain="garmin.com")
        try:
            client.login(email, password)
        except Exception as e:
            logger.warning(f"Echec login Garmin: {type(e).__name__}: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identifiants Garmin invalides",
            )

        try:
            token_data = client.dumps()
        except Exception as e:
            logger.error(f"Echec serialisation token Garth: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la serialisation du token Garmin",
            )

        return self.encrypt_token(token_data)

    def get_client(self, encrypted_token: str) -> garth.Client:
        """
        Reconstruit un client Garth a partir d'un token chiffre,
        sans re-login.

        Args:
            encrypted_token: Token Garth chiffre

        Returns:
            Instance garth.Client prete a l'emploi
        """
        token_data = self.decrypt_token(encrypted_token)
        client = garth.Client(domain="garmin.com")
        try:
            client.loads(token_data)
        except Exception as e:
            logger.error(f"Echec restauration client Garth: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token Garmin invalide ou expire, reconnexion necessaire",
            )
        return client

    def encrypt_token(self, token: str) -> str:
        """Chiffre un token Garth pour le stockage"""
        if not self.cipher:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Encryption non configuree: ENCRYPTION_KEY manquante",
            )
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token vide fourni pour le chiffrement",
            )
        try:
            return self.cipher.encrypt(token.encode()).decode()
        except Exception as e:
            logger.error(f"Erreur chiffrement token: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Echec du chiffrement du token",
            )

    def decrypt_token(self, encrypted_token: str) -> str:
        """Dechiffre un token Garth stocke"""
        if not self.cipher:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Encryption non configuree: ENCRYPTION_KEY manquante",
            )
        if not encrypted_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token chiffre vide fourni pour le dechiffrement",
            )
        try:
            return self.cipher.decrypt(encrypted_token.encode()).decode()
        except Exception as e:
            logger.error(f"Erreur dechiffrement token: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Echec du dechiffrement du token Garmin",
            )


garmin_auth = GarminAuthManager()
