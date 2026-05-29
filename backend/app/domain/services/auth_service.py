"""
Service d'authentification : signup, login, OAuth Strava/Google, refresh tokens.
"""
import logging
from sqlmodel import Session, select
from uuid import UUID
from datetime import datetime

from app.auth.jwt import jwt_manager, password_manager, TokenResponse
from app.auth.strava_oauth import strava_oauth
from app.auth.google_oauth import google_oauth
from app.auth.garmin_auth import garmin_auth
from app.domain.entities import User, UserCreate, StravaAuth, GoogleAuth, GarminAuth
from app.domain.services.garmin_cache import garmin_token_cache

logger = logging.getLogger(__name__)


class AuthService:

    def signup(self, session: Session, user_data: UserCreate) -> TokenResponse:
        existing_user = session.exec(
            select(User).where(User.email == user_data.email)
        ).first()
        if existing_user:
            raise ValueError("Email already registered")

        hashed_password = password_manager.hash_password(user_data.password)
        db_user = User(
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
        )
        session.add(db_user)
        session.commit()
        session.refresh(db_user)

        return jwt_manager.create_token_pair(str(db_user.id), db_user.email)

    def login(self, session: Session, email: str, password: str) -> TokenResponse:
        user = session.exec(select(User).where(User.email == email)).first()

        if not user or not password_manager.verify_password(password, user.hashed_password):
            raise ValueError("Incorrect email or password")

        if not user.is_active:
            raise ValueError("Inactive user")

        return jwt_manager.create_token_pair(str(user.id), user.email)

    def get_user(self, session: Session, user_id: str) -> User:
        user = session.get(User, UUID(user_id))
        if not user:
            raise ValueError("User not found")
        return user

    # ---- Google OAuth ----

    def get_google_status(self, session: Session, user_id: str) -> dict:
        google_auth_record = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()

        if not google_auth_record:
            return {
                "connected": False,
                "google_user_id": None,
                "scope": None,
                "expires_at": None,
                "is_expired": True,
            }

        is_expired = (
            google_auth_record.expires_at < datetime.now()
            if google_auth_record.expires_at
            else True
        )

        return {
            "connected": True,
            "google_user_id": google_auth_record.user_id,
            "scope": google_auth_record.scope,
            "expires_at": google_auth_record.expires_at.isoformat() if google_auth_record.expires_at else None,
            "is_expired": is_expired,
        }

    def refresh_google_token(self, session: Session, user_id: str) -> dict:
        google_auth_record = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()

        if not google_auth_record:
            raise ValueError("Aucune authentification Google trouvee")

        refresh_token = google_oauth.decrypt_token(google_auth_record.refresh_token_encrypted)
        new_tokens = google_oauth.refresh_access_token(refresh_token)

        encrypted_access_token = google_oauth.encrypt_token(new_tokens.access_token)
        encrypted_refresh_token = google_oauth.encrypt_token(new_tokens.refresh_token)

        google_auth_record.access_token_encrypted = encrypted_access_token
        google_auth_record.refresh_token_encrypted = encrypted_refresh_token
        google_auth_record.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
        google_auth_record.updated_at = datetime.now()

        session.add(google_auth_record)
        session.commit()

        return {
            "success": True,
            "message": "Token rafraichi avec succes",
            "expires_at": google_auth_record.expires_at.isoformat(),
            "is_expired": False,
        }

    def handle_google_callback(self, session: Session, code: str) -> tuple:
        """Retourne (user, jwt_tokens, google_user_id)."""
        tokens = google_oauth.exchange_code_for_tokens(code)
        user_info = google_oauth.get_user_info(tokens.access_token)

        user = session.exec(
            select(User).where(User.email == user_info["email"])
        ).first()

        if not user:
            user = User(
                email=user_info["email"],
                full_name=user_info.get("name", ""),
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)

        encrypted_access_token = google_oauth.encrypt_token(tokens.access_token)
        encrypted_refresh_token = google_oauth.encrypt_token(tokens.refresh_token)

        google_auth_record = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == user.id)
        ).first()

        if google_auth_record:
            google_auth_record.access_token_encrypted = encrypted_access_token
            google_auth_record.refresh_token_encrypted = encrypted_refresh_token
            google_auth_record.expires_at = datetime.fromtimestamp(tokens.expires_at)
            google_auth_record.scope = tokens.scope
            google_auth_record.google_user_id = tokens.google_user_id
        else:
            google_auth_record = GoogleAuth(
                user_id=user.id,
                google_user_id=tokens.google_user_id,
                access_token_encrypted=encrypted_access_token,
                refresh_token_encrypted=encrypted_refresh_token,
                expires_at=datetime.fromtimestamp(tokens.expires_at),
                scope=tokens.scope,
            )
            session.add(google_auth_record)

        session.commit()

        jwt_tokens = jwt_manager.create_token_pair(str(user.id), user.email)
        return user, jwt_tokens, tokens.google_user_id

    # ---- Strava OAuth ----

    def handle_strava_callback(self, session: Session, code: str, state: str) -> tuple:
        """Retourne (athlete_id,). Leve ValueError si state invalide ou user introuvable."""
        tokens = strava_oauth.exchange_code_for_tokens(code)
        logger.info(f"Tokens recus pour l'athlete {tokens.athlete_id}")

        try:
            user = session.get(User, UUID(state))
        except ValueError:
            raise ValueError("Identifiant d'etat invalide")

        if not user:
            raise ValueError("Utilisateur non trouve")

        encrypted_access = strava_oauth.encrypt_token(tokens.access_token)
        encrypted_refresh = strava_oauth.encrypt_token(tokens.refresh_token)

        existing_auth = session.exec(
            select(StravaAuth).where(StravaAuth.user_id == user.id)
        ).first()

        if existing_auth:
            existing_auth.access_token_encrypted = encrypted_access
            existing_auth.refresh_token_encrypted = encrypted_refresh
            existing_auth.expires_at = datetime.fromtimestamp(tokens.expires_at)
            existing_auth.scope = tokens.scope
            existing_auth.updated_at = datetime.utcnow()
        else:
            strava_auth = StravaAuth(
                user_id=user.id,
                strava_athlete_id=tokens.athlete_id,
                access_token_encrypted=encrypted_access,
                refresh_token_encrypted=encrypted_refresh,
                expires_at=datetime.fromtimestamp(tokens.expires_at),
                scope=tokens.scope,
            )
            session.add(strava_auth)

        session.commit()
        return (tokens.athlete_id,)

    def get_strava_status(self, session: Session, user_id: str) -> dict:
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
            "last_sync": strava_auth.updated_at,
        }

    def get_valid_google_token(self, session: Session, user_id: str) -> str:
        """Verifie et rafraichit le token Google si necessaire. Retourne le token dechiffre."""
        google_auth_record = session.exec(
            select(GoogleAuth).where(GoogleAuth.user_id == UUID(user_id))
        ).first()

        if not google_auth_record:
            raise ValueError("Utilisateur non connecte a Google Calendar")

        is_expired = (
            google_auth_record.expires_at < datetime.now()
            if google_auth_record.expires_at
            else True
        )

        if is_expired:
            logger.info("Token Google expire, rafraichissement automatique...")
            refresh_token = google_oauth.decrypt_token(google_auth_record.refresh_token_encrypted)
            new_tokens = google_oauth.refresh_access_token(refresh_token)

            encrypted_access_token = google_oauth.encrypt_token(new_tokens.access_token)
            encrypted_refresh_token = google_oauth.encrypt_token(new_tokens.refresh_token)

            google_auth_record.access_token_encrypted = encrypted_access_token
            google_auth_record.refresh_token_encrypted = encrypted_refresh_token
            google_auth_record.expires_at = datetime.fromtimestamp(new_tokens.expires_at)
            google_auth_record.updated_at = datetime.now()

            session.add(google_auth_record)
            session.commit()
            logger.info("Token Google rafraichi avec succes")

        return google_oauth.decrypt_token(google_auth_record.access_token_encrypted)

    # ---- Garmin Connect ----

    def handle_garmin_login(self, session: Session, user_id: str, email: str, password: str) -> dict:
        """
        Login Garmin one-time : authentifie via Garth, stocke le token chiffre.
        Email et mot de passe ne sont JAMAIS stockes.
        Token mis en cache en mémoire pour éviter les re-authentifications inutiles.
        """
        encrypted_token = garmin_auth.login(email, password)
        user_uuid = UUID(user_id)

        existing = session.exec(
            select(GarminAuth).where(GarminAuth.user_id == user_uuid)
        ).first()

        if existing:
            existing.oauth_token_encrypted = encrypted_token
            existing.token_created_at = datetime.utcnow()
            existing.updated_at = datetime.utcnow()
        else:
            new_auth = GarminAuth(
                user_id=user_uuid,
                oauth_token_encrypted=encrypted_token,
                token_created_at=datetime.utcnow(),
            )
            session.add(new_auth)

        session.commit()

        # Mettre le token en cache pour éviter les re-auth inutiles
        garmin_token_cache.set(user_uuid, encrypted_token)
        logger.info(f"Garmin connecte pour user {user_id} (token mis en cache)")

        return {"connected": True, "message": "Garmin Connect lie avec succes"}

    def get_garmin_status(self, session: Session, user_id: str) -> dict:
        """Retourne le statut de connexion Garmin pour un utilisateur."""
        garmin_auth_record = session.exec(
            select(GarminAuth).where(GarminAuth.user_id == UUID(user_id))
        ).first()

        if not garmin_auth_record:
            return {"connected": False}

        return {
            "connected": True,
            "display_name": garmin_auth_record.garmin_display_name,
            "garmin_display_name": garmin_auth_record.garmin_display_name,
            "token_created_at": garmin_auth_record.token_created_at,
            "last_sync_at": garmin_auth_record.last_sync_at,
        }

    def disconnect_garmin(self, session: Session, user_id: str) -> dict:
        """Supprime l'authentification Garmin d'un utilisateur."""
        user_uuid = UUID(user_id)
        garmin_auth_record = session.exec(
            select(GarminAuth).where(GarminAuth.user_id == user_uuid)
        ).first()

        if not garmin_auth_record:
            raise ValueError("Aucune connexion Garmin trouvee")

        session.delete(garmin_auth_record)
        session.commit()

        # Invalider le token du cache
        garmin_token_cache.invalidate(user_uuid)
        logger.info(f"Garmin deconnecte pour user {user_id} (cache invalidé)")

        return {"connected": False, "message": "Garmin Connect deconnecte"}

    def verify_garmin_token(self, session: Session, user_id: str) -> dict:
        """Vérifie que le token Garmin de l'utilisateur est toujours valide."""
        user_uuid = UUID(user_id)
        garmin_auth_record = session.exec(
            select(GarminAuth).where(GarminAuth.user_id == user_uuid)
        ).first()

        if not garmin_auth_record:
            return {"connected": False, "valid": False, "message": "Aucune connexion Garmin"}

        try:
            # Essayer de décrypter et utiliser le token
            decrypted_token = garmin_auth.decrypt_token(garmin_auth_record.oauth_token_encrypted)

            # Vérifier que le token n'est pas expiré (token créé < 90 jours)
            if garmin_auth_record.token_created_at:
                age_days = (datetime.utcnow() - garmin_auth_record.token_created_at).days
                if age_days > 90:
                    logger.warning(f"Token Garmin expiré pour user {user_id} (age: {age_days} jours)")
                    return {
                        "connected": True,
                        "valid": False,
                        "message": "Token expiré, veuillez vous reconnecter",
                        "expired": True,
                    }

            logger.info(f"Token Garmin valide pour user {user_id}")
            return {
                "connected": True,
                "valid": True,
                "message": "Token valide",
                "token_age_days": age_days if garmin_auth_record.token_created_at else None,
            }
        except Exception as e:
            logger.error(f"Erreur verification token Garmin pour user {user_id}: {e}")
            return {
                "connected": True,
                "valid": False,
                "message": "Erreur lors de la vérification du token",
                "error": str(e),
            }


auth_service = AuthService()
