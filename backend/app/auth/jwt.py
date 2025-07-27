"""
Gestion des tokens JWT pour l'authentification
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status
from pydantic import BaseModel

from app.core.settings import get_settings

settings = get_settings()

# Configuration du hashage des mots de passe
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenData(BaseModel):
    """Données contenues dans un token"""
    user_id: str
    email: str
    exp: datetime


class TokenResponse(BaseModel):
    """Réponse d'authentification avec tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class JWTManager:
    """Gestionnaire des tokens JWT"""
    
    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Crée un access token JWT"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire, "type": "access"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Crée un refresh token JWT"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_token_pair(self, user_id: str, email: str) -> TokenResponse:
        """Crée une paire access/refresh token"""
        token_data = {"sub": str(user_id), "email": email}
        
        access_token = self.create_access_token(token_data)
        refresh_token = self.create_refresh_token(token_data)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self.access_token_expire_minutes * 60
        )
    
    def verify_token(self, token: str, token_type: str = "access") -> TokenData:
        """Vérifie et décode un token JWT"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Vérifier le type de token
            if payload.get("type") != token_type:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token type. Expected {token_type}"
                )
            
            user_id: str = payload.get("sub")
            email: str = payload.get("email")
            exp: datetime = datetime.fromtimestamp(payload.get("exp"))
            
            if user_id is None or email is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token payload"
                )
            
            return TokenData(user_id=user_id, email=email, exp=exp)
            
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
    
    def refresh_access_token(self, refresh_token: str) -> str:
        """Génère un nouvel access token à partir d'un refresh token"""
        token_data = self.verify_token(refresh_token, token_type="refresh")
        
        # Créer un nouvel access token
        new_token_data = {"sub": token_data.user_id, "email": token_data.email}
        return self.create_access_token(new_token_data)


class PasswordManager:
    """Gestionnaire des mots de passe"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hashe un mot de passe"""
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Vérifie un mot de passe"""
        return pwd_context.verify(plain_password, hashed_password)


# Instances globales
jwt_manager = JWTManager()
password_manager = PasswordManager()


def get_current_user_id(token: str) -> str:
    """Extrait l'ID utilisateur du token (pour dependency injection)"""
    token_data = jwt_manager.verify_token(token)
    return token_data.user_id 