"""
Service Google Calendar avec OAuth
Utilise l'API Google Calendar avec authentification OAuth
"""
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import HTTPException, status
import logging
import os
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Service Google Calendar avec OAuth"""
    
    def __init__(self):
        self.base_url = "https://www.googleapis.com/calendar/v3"
        self.oauth_base_url = "https://accounts.google.com"
        self.token_url = "https://oauth2.googleapis.com/token"
        
        # Utiliser les settings pour charger les variables d'environnement
        from app.core.settings import get_settings
        settings = get_settings()
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
        self.api_key = None  # Optionnel pour les requêtes publiques
    
    def get_authorization_url(self) -> str:
        """
        Génère l'URL d'autorisation Google OAuth
        
        Returns:
            URL d'autorisation Google
        """
        if not self.client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GOOGLE_CLIENT_ID non configuré"
            )
        
        if not self.redirect_uri:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GOOGLE_REDIRECT_URI non configuré"
            )
        
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile",
            "access_type": "offline",
            "prompt": "consent"
        }
        
        auth_url = f"{self.oauth_base_url}/o/oauth2/v2/auth?{urlencode(params)}"
        return auth_url
    
    def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Échange le code d'autorisation contre des tokens
        
        Args:
            code: Code d'autorisation de Google
            
        Returns:
            Dictionnaire contenant les tokens
        """
        if not self.client_id or not self.client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuration Google OAuth incomplète"
            )
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }
        
        try:
            response = requests.post(self.token_url, data=data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de l'échange du code: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Erreur lors de l'échange du code d'autorisation"
            )
    
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Récupère les informations de l'utilisateur
        
        Args:
            access_token: Token d'accès Google
            
        Returns:
            Informations de l'utilisateur
        """
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers=headers
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la récupération des infos utilisateur: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Erreur lors de la récupération des informations utilisateur"
            )

    def get_user_calendars(self, access_token: str) -> List[Dict[str, Any]]:
        """
        Récupère les calendriers de l'utilisateur
        
        Args:
            access_token: Token d'accès Google (optionnel pour calendriers publics)
            
        Returns:
            Liste des calendriers
        """
        try:
            headers = {}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            
            response = requests.get(
                f"{self.base_url}/users/me/calendarList",
                headers=headers
            )
            
            if response.status_code == 401:
                # Si pas d'authentification, on peut essayer les calendriers publics
                logger.info("Pas d'authentification Google, utilisation des calendriers publics")
                return self._get_public_calendars()
            
            response.raise_for_status()
            data = response.json()
            
            calendars = []
            for calendar in data.get("items", []):
                calendars.append({
                    "id": calendar["id"],
                    "summary": calendar.get("summary", "Sans nom"),
                    "description": calendar.get("description", ""),
                    "accessRole": calendar.get("accessRole", "none"),
                    "primary": calendar.get("primary", False)
                })
            
            return calendars
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la récupération des calendriers: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la récupération des calendriers Google"
            )
    
    def _get_public_calendars(self) -> List[Dict[str, Any]]:
        """Récupère les calendriers publics par défaut"""
        return [
            {
                "id": "primary",
                "summary": "Calendrier principal",
                "description": "Votre calendrier principal Google",
                "accessRole": "owner",
                "primary": True
            }
        ]
    
    def export_workout_plans_to_google(
        self, 
        workout_plans: List[Dict[str, Any]], 
        calendar_id: str = "primary",
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Exporte les plans d'entraînement vers Google Calendar
        
        Args:
            workout_plans: Liste des plans d'entraînement
            calendar_id: ID du calendrier Google
            access_token: Token d'accès Google (optionnel)
            
        Returns:
            Résultat de l'export
        """
        try:
            headers = {"Content-Type": "application/json"}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            
            exported_count = 0
            errors = []
            
            for plan in workout_plans:
                try:
                    # Créer l'événement Google Calendar
                    event = {
                        "summary": f"🏃‍♂️ {plan.get('workout_type', 'Entraînement')}",
                        "description": plan.get('description', ''),
                        "start": {
                            "dateTime": plan['planned_date'],
                            "timeZone": "Europe/Paris"
                        },
                        "end": {
                            "dateTime": (datetime.fromisoformat(plan['planned_date']) + timedelta(hours=1)).isoformat(),
                            "timeZone": "Europe/Paris"
                        },
                        "reminders": {
                            "useDefault": False,
                            "overrides": [
                                {"method": "popup", "minutes": 30}
                            ]
                        }
                    }
                    
                    response = requests.post(
                        f"{self.base_url}/calendars/{calendar_id}/events",
                        headers=headers,
                        json=event
                    )
                    
                    if response.status_code == 200:
                        exported_count += 1
                    else:
                        errors.append(f"Erreur pour {plan.get('workout_type', 'Entraînement')}: {response.status_code}")
                        
                except Exception as e:
                    errors.append(f"Erreur pour {plan.get('workout_type', 'Entraînement')}: {str(e)}")
            
            return {
                "exported_count": exported_count,
                "total_count": len(workout_plans),
                "errors": errors,
                "success": exported_count > 0
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de l'export vers Google Calendar: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de l'export vers Google Calendar"
            )
    
    def import_google_calendar_as_workout_plans(
        self,
        calendar_id: str = "primary",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Importe les événements Google Calendar comme plans d'entraînement
        
        Args:
            calendar_id: ID du calendrier Google
            start_date: Date de début (optionnel)
            end_date: Date de fin (optionnel)
            access_token: Token d'accès Google (optionnel)
            
        Returns:
            Liste des plans d'entraînement importés
        """
        try:
            headers = {}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            
            # Paramètres de requête
            params = {
                "singleEvents": True,
                "orderBy": "startTime"
            }
            
            if start_date:
                params["timeMin"] = f"{start_date}T00:00:00Z"
            if end_date:
                params["timeMax"] = f"{end_date}T23:59:59Z"
            
            response = requests.get(
                f"{self.base_url}/calendars/{calendar_id}/events",
                headers=headers,
                params=params
            )
            
            if response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Accès non autorisé au calendrier Google"
                )
            
            response.raise_for_status()
            data = response.json()
            
            workout_plans = []
            for event in data.get("items", []):
                # Filtrer pour ne garder que les événements sportifs/entraînement
                summary = event.get("summary", "").lower()
                description = event.get("description", "").lower()
                
                # Mots-clés pour identifier les entraînements sportifs
                sport_keywords = [
                    "course", "running", "jogging", "entraînement", "workout", "sport",
                    "footing", "marche", "vélo", "cyclisme", "natation", "nager",
                    "musculation", "gym", "fitness", "séance", "seuil", "fractionné",
                    "endurance", "récupération", "🏃", "🚴", "🏊", "💪"
                ]
                
                # Vérifier si l'événement contient des mots-clés sportifs
                is_sport_event = any(keyword in summary for keyword in sport_keywords) or \
                                any(keyword in description for keyword in sport_keywords)
                
                if summary and is_sport_event:  # Seulement les événements sportifs avec un titre
                    start = event.get("start", {})
                    start_time = start.get("dateTime") or start.get("date")
                    
                    # Calculer la durée de l'événement
                    end = event.get("end", {})
                    end_time = end.get("dateTime") or end.get("date")
                    
                    duration_minutes = 60  # Par défaut
                    if start_time and end_time:
                        try:
                            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                            duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
                        except:
                            duration_minutes = 60
                    
                    workout_plans.append({
                        "summary": event.get("summary", "Entraînement"),  # Titre de l'événement
                        "description": event.get("description", ""),  # Description de l'événement
                        "planned_date": start_time,
                        "duration_minutes": duration_minutes,
                        "is_completed": False,
                        "source": "google_calendar"
                    })
            
            return workout_plans
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de l'import depuis Google Calendar: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de l'import depuis Google Calendar"
            )

    def get_calendar_events_raw_data(
        self,
        calendar_id: str = "primary",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        access_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Récupère toutes les données brutes des événements Google Calendar
        
        Args:
            calendar_id: ID du calendrier Google
            start_date: Date de début (optionnel)
            end_date: Date de fin (optionnel)
            access_token: Token d'accès Google (optionnel)
            
        Returns:
            Dictionnaire contenant toutes les informations du calendrier et ses événements
        """
        try:
            headers = {}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            
            # Paramètres de requête pour récupérer TOUS les événements
            params = {
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": 2500  # Maximum autorisé par Google
            }
            
            if start_date:
                params["timeMin"] = f"{start_date}T00:00:00Z"
            if end_date:
                params["timeMax"] = f"{end_date}T23:59:59Z"
            
            response = requests.get(
                f"{self.base_url}/calendars/{calendar_id}/events",
                headers=headers,
                params=params
            )
            
            if response.status_code == 401:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Accès non autorisé au calendrier Google"
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Récupérer les informations du calendrier
            calendar_info_response = requests.get(
                f"{self.base_url}/calendars/{calendar_id}",
                headers=headers
            )
            calendar_info = {}
            if calendar_info_response.status_code == 200:
                calendar_info = calendar_info_response.json()
            
            # Structurer les données de sortie
            calendar_data = {
                "calendar_info": {
                    "id": calendar_info.get("id", calendar_id),
                    "summary": calendar_info.get("summary", "Calendrier"),
                    "description": calendar_info.get("description", ""),
                    "timeZone": calendar_info.get("timeZone", "Europe/Paris"),
                    "accessRole": calendar_info.get("accessRole", "none"),
                    "primary": calendar_info.get("primary", False),
                    "updated": calendar_info.get("updated", ""),
                    "etag": calendar_info.get("etag", "")
                },
                "events": []
            }
            
            # Traiter chaque événement avec toutes ses informations
            for event in data.get("items", []):
                event_data = {
                    "id": event.get("id", ""),
                    "summary": event.get("summary", ""),
                    "description": event.get("description", ""),
                    "location": event.get("location", ""),
                    "start": event.get("start", {}),
                    "end": event.get("end", {}),
                    "duration": event.get("duration", ""),
                    "allDay": event.get("allDay", False),
                    "recurringEventId": event.get("recurringEventId", ""),
                    "originalStartTime": event.get("originalStartTime", {}),
                    "attendees": event.get("attendees", []),
                    "organizer": event.get("organizer", {}),
                    "creator": event.get("creator", {}),
                    "created": event.get("created", ""),
                    "updated": event.get("updated", ""),
                    "status": event.get("status", ""),
                    "transparency": event.get("transparency", ""),
                    "visibility": event.get("visibility", ""),
                    "iCalUID": event.get("iCalUID", ""),
                    "sequence": event.get("sequence", 0),
                    "attendeesOmitted": event.get("attendeesOmitted", False),
                    "guestsCanModify": event.get("guestsCanModify", False),
                    "guestsCanInviteOthers": event.get("guestsCanInviteOthers", False),
                    "guestsCanSeeOtherGuests": event.get("guestsCanSeeOtherGuests", False),
                    "privateCopy": event.get("privateCopy", False),
                    "reminders": event.get("reminders", {}),
                    "source": event.get("source", {}),
                    "htmlLink": event.get("htmlLink", ""),
                    "hangoutLink": event.get("hangoutLink", ""),
                    "conferenceData": event.get("conferenceData", {}),
                    "gadget": event.get("gadget", {}),
                    "anyoneCanAddSelf": event.get("anyoneCanAddSelf", False),
                    "guestsCanModify": event.get("guestsCanModify", False),
                    "guestsCanInviteOthers": event.get("guestsCanInviteOthers", False),
                    "guestsCanSeeOtherGuests": event.get("guestsCanSeeOtherGuests", False),
                    "privateCopy": event.get("privateCopy", False),
                    "locked": event.get("locked", False),
                    "colorId": event.get("colorId", ""),
                    "etag": event.get("etag", ""),
                    "eventType": event.get("eventType", ""),
                    "extendedProperties": event.get("extendedProperties", {}),
                    "outOfOfficeProperties": event.get("outOfOfficeProperties", {}),
                    "focusTimeProperties": event.get("focusTimeProperties", {}),
                    "workingLocationProperties": event.get("workingLocationProperties", {}),
                    "conferenceDataVersion": event.get("conferenceDataVersion", 0),
                    "attendeesOmitted": event.get("attendeesOmitted", False),
                    "guestsCanModify": event.get("guestsCanModify", False),
                    "guestsCanInviteOthers": event.get("guestsCanInviteOthers", False),
                    "guestsCanSeeOtherGuests": event.get("guestsCanSeeOtherGuests", False),
                    "privateCopy": event.get("privateCopy", False),
                    "reminders": event.get("reminders", {}),
                    "source": event.get("source", {}),
                    "htmlLink": event.get("htmlLink", ""),
                    "hangoutLink": event.get("hangoutLink", ""),
                    "conferenceData": event.get("conferenceData", {}),
                    "gadget": event.get("gadget", {}),
                    "anyoneCanAddSelf": event.get("anyoneCanAddSelf", False),
                    "guestsCanModify": event.get("guestsCanModify", False),
                    "guestsCanInviteOthers": event.get("guestsCanInviteOthers", False),
                    "guestsCanSeeOtherGuests": event.get("guestsCanSeeOtherGuests", False),
                    "privateCopy": event.get("privateCopy", False),
                    "locked": event.get("locked", False),
                    "colorId": event.get("colorId", ""),
                    "etag": event.get("etag", ""),
                    "eventType": event.get("eventType", ""),
                    "extendedProperties": event.get("extendedProperties", {}),
                    "outOfOfficeProperties": event.get("outOfOfficeProperties", {}),
                    "focusTimeProperties": event.get("focusTimeProperties", {}),
                    "workingLocationProperties": event.get("workingLocationProperties", {}),
                    "conferenceDataVersion": event.get("conferenceDataVersion", 0)
                }
                
                calendar_data["events"].append(event_data)
            
            # Ajouter des métadonnées
            calendar_data["metadata"] = {
                "export_date": datetime.now().isoformat(),
                "total_events": len(calendar_data["events"]),
                "calendar_id": calendar_id,
                "start_date": start_date,
                "end_date": end_date,
                "api_version": "v3"
            }
            
            return calendar_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Erreur lors de la récupération des données brutes Google Calendar: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la récupération des données Google Calendar"
            )


# Instance globale du service
google_calendar_service = GoogleCalendarService() 