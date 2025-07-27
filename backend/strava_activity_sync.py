#!/usr/bin/env python3
"""
strava_activity_sync.py – Daemon d'ingestion Strava COMPLET
===========================================================

Rôle
----
* Surveille **stridelta.db** (SQLite) → table `activity` pour détecter les nouvelles
  activités (champ `strava_id`).
* Pour chaque ID détecté, appelle l'API Strava pour récupérer TOUS les détails :
  - GET /activities/{id}?include_all_efforts=true → DetailedActivity
  - GET /activities/{id}/laps → laps  
  - GET /activities/{id}/streams → streams
  - GET /segments/{seg_id} → segments (pour chaque effort)
* Alimente **activity_detail.db** avec toutes les tables normalisées.

Configuration par variables d'environnement :
    STRIDELTA_DB (déf. "stridelta.db")
    DETAIL_DB    (déf. "activity_detail.db")
    POLL_INTERVAL (secondes, déf. 30)
"""

import json
import logging
import os
import sqlite3
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

import requests

# Essayer de charger python-dotenv si disponible
try:
    from dotenv import load_dotenv
    # Charger .env.sqlite en priorité, puis .env
    if os.path.exists('.env.sqlite'):
        load_dotenv('.env.sqlite')
        logging.debug("Variables chargées depuis .env.sqlite")
    elif os.path.exists('.env'):
        load_dotenv('.env')
        logging.debug("Variables chargées depuis .env")
except ImportError:
    logging.debug("python-dotenv non disponible, utilisation des variables d'environnement uniquement")

# --- Configuration ---------------------------------------------------------
# Configuration Strava
STRIDELTA_DB = os.getenv("STRIDELTA_DB", "stridedelta.db")
DETAIL_DB = os.getenv("DETAIL_DB", "activity_detail.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# Rate limiting
_last_request_time = 0
_request_count = 0
_window_start = 0

# --- Helpers OAuth / API ---------------------------------------------------

def refresh_access_token(refresh_token_encrypted: str) -> tuple[str, str, str]:
    """Actualise l'access token avec le refresh token"""
    try:
        # Décrypter le refresh token
        from cryptography.fernet import Fernet
        import os
        from dotenv import load_dotenv
        
        # Charger la clé d'encryption
        if os.path.exists('.env.sqlite'):
            load_dotenv('.env.sqlite')
        elif os.path.exists('.env'):
            load_dotenv('.env')
        
        encryption_key = os.getenv("ENCRYPTION_KEY")
        if not encryption_key:
            raise Exception("ENCRYPTION_KEY manquante")
        
        cipher = Fernet(encryption_key.encode())
        refresh_token = cipher.decrypt(refresh_token_encrypted.encode()).decode()
        
        # Appel API pour rafraîchir le token
        import requests
        
        token_url = "https://www.strava.com/api/v3/oauth/token"
        data = {
            "client_id": os.getenv("STRAVA_CLIENT_ID"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET"),
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        response = requests.post(token_url, data=data, timeout=30)
        response.raise_for_status()
        
        token_data = response.json()
        
        # Chiffrer le nouveau access token
        new_access_token = token_data["access_token"]
        new_refresh_token = token_data["refresh_token"]
        new_expires_at = token_data["expires_at"]
        
        new_access_encrypted = cipher.encrypt(new_access_token.encode()).decode()
        new_refresh_encrypted = cipher.encrypt(new_refresh_token.encode()).decode()
        
        # Mettre à jour la base de données
        with sqlite3.connect(STRIDELTA_DB) as conn:
            conn.execute("""
                UPDATE stravaauth 
                SET access_token_encrypted = ?, refresh_token_encrypted = ?, expires_at = ?
                WHERE refresh_token_encrypted = ?
            """, (new_access_encrypted, new_refresh_encrypted, 
                  datetime.fromtimestamp(new_expires_at).isoformat(), refresh_token_encrypted))
            conn.commit()
        
        logging.info("✅ Token rafraîchi avec succès")
        return new_access_token, new_refresh_encrypted, datetime.fromtimestamp(new_expires_at).isoformat()
        
    except Exception as e:
        logging.error(f"❌ Erreur lors du rafraîchissement du token: {e}")
        raise


def get_access_token() -> str:
    """Récupère un token d'accès Strava depuis la base de données."""
    try:
        # Récupérer les tokens depuis la base de données
        with sqlite3.connect(STRIDELTA_DB) as conn:
            cursor = conn.execute("""
                SELECT access_token_encrypted, refresh_token_encrypted, expires_at
                FROM stravaauth 
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if not row:
                raise Exception("Aucun token Strava trouvé dans la base de données")
            
            access_encrypted, refresh_encrypted, expires_at = row
            
            # Décrypter le token
            from cryptography.fernet import Fernet
            import os
            from dotenv import load_dotenv
            
            # Charger la clé d'encryption
            if os.path.exists('.env.sqlite'):
                load_dotenv('.env.sqlite')
            elif os.path.exists('.env'):
                load_dotenv('.env')
            
            encryption_key = os.getenv("ENCRYPTION_KEY")
            if not encryption_key:
                raise Exception("ENCRYPTION_KEY manquante")
            
            cipher = Fernet(encryption_key.encode())
            access_token = cipher.decrypt(access_encrypted.encode()).decode()
            
            # Vérifier si le token a expiré
            from datetime import datetime
            if expires_at and datetime.fromisoformat(expires_at.replace('Z', '+00:00')) < datetime.now():
                logging.warning("Token expiré, rafraîchissement automatique...")
                # Rafraîchir automatiquement le token
                new_access_token, new_refresh_encrypted, new_expires_at = refresh_access_token(refresh_encrypted)
                logging.info(f"✅ Token rafraîchi automatiquement (expire: {new_expires_at})")
                return new_access_token
            
            logging.info(f"✅ Token récupéré depuis la base (expire: {expires_at})")
            return access_token
            
    except Exception as e:
        logging.error(f"❌ Erreur récupération token: {e}")
        raise


def safe_get(url: str, token: str, params: Dict = None) -> Dict:
    """Appel API avec rate limiting (100 req/15min, 1000/jour)."""
    global _last_request_time, _request_count, _window_start
    
    now = time.time()
    
    # Reset window si > 15 min
    if now - _window_start > 900:  # 15 min
        _window_start = now
        _request_count = 0
    
    # Rate limit: max 100 req/15min
    if _request_count >= 100:
        wait_time = 900 - (now - _window_start)
        if wait_time > 0:
            logging.warning(f"Rate limit atteint, pause {wait_time:.0f}s")
            time.sleep(wait_time)
            _window_start = time.time()
            _request_count = 0
    
    # Minimum 200ms entre requêtes  
    elapsed = now - _last_request_time
    if elapsed < 0.2:
        time.sleep(0.2 - elapsed)
    
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, params=params or {}, headers=headers, timeout=20)
    resp.raise_for_status()
    
    _last_request_time = time.time()
    _request_count += 1
    
    return resp.json()


def fetch_activity_details(activity_id: int, token: str) -> Dict:
    """Récupère les détails complets d'une activité."""
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    params = {"include_all_efforts": "true"}
    return safe_get(url, token, params)


def fetch_activity_laps(activity_id: int, token: str) -> List[Dict]:
    """Récupère les laps d'une activité."""
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/laps"
    return safe_get(url, token)


def fetch_activity_streams(activity_id: int, token: str) -> Dict:
    """Récupère les streams d'une activité."""
    url = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    params = {
        "keys": "time,distance,latlng,altitude,velocity_smooth,heartrate,cadence,watts,temp,moving,grade_smooth",
        "key_by_type": "true"
    }
    try:
        return safe_get(url, token, params)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.debug(f"Pas de streams pour activité {activity_id}")
            return {}
        raise


def fetch_segment_details(segment_id: int, token: str) -> Dict:
    """Récupère les détails d'un segment."""
    url = f"https://www.strava.com/api/v3/segments/{segment_id}"
    return safe_get(url, token)


# --- SQLite utilitaires ----------------------------------------------------

def ensure_processed_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_activities (
            activity_id INTEGER PRIMARY KEY,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def get_new_activity_ids(conn: sqlite3.Connection) -> List[int]:
    """Sélectionne les strava_id encore non traités."""
    rows = conn.execute(
        """
        SELECT strava_id
          FROM activity
         WHERE strava_id IS NOT NULL 
           AND strava_id NOT IN (SELECT activity_id FROM processed_activities)
         ORDER BY strava_id ASC
        """
    ).fetchall()
    return [row[0] for row in rows]


def mark_as_processed(conn: sqlite3.Connection, activity_id: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO processed_activities(activity_id) VALUES (?)",
        (activity_id,),
    )
    conn.commit()


# --- Insertion dans activity_detail.db -------------------------------------

def safe_get_value(data: dict, key: str, default=None):
    """Récupère une valeur de manière sécurisée avec gestion des listes vides."""
    try:
        value = data.get(key, default)
        # Si c'est une liste vide, retourner le default
        if isinstance(value, list) and len(value) == 0:
            return default
        return value
    except (IndexError, KeyError, TypeError):
        return default

def safe_get_list_item(data: list, index: int, default=None):
    """Récupère un élément de liste de manière sécurisée."""
    try:
        if isinstance(data, list) and len(data) > index:
            return data[index]
        return default
    except (IndexError, TypeError):
        return default


def insert_athlete(conn: sqlite3.Connection, athlete_data: Dict) -> None:
    """Insert/update athlete."""
    if not athlete_data:
        return
        
    conn.execute(
        """
        INSERT OR REPLACE INTO athletes (athlete_id, resource_state)
        VALUES (?, ?)
        """,
        (
            athlete_data.get("id"),
            athlete_data.get("resource_state"),
        ),
    )


def detect_real_activity_type(activity_data: dict) -> str:
    """Détecte le vrai type d'activité basé sur le nom et les métriques."""
    name = safe_get_value(activity_data, 'name', '').lower()
    sport_type = safe_get_value(activity_data, 'type', '').lower()
    
    # Détection par nom - plus précise et moins agressive
    padel_keywords = ['padel', 'tennis', 'badminton', 'squash', 'raquette', 'racket']
    workout_keywords = ['gym', 'muscu', 'musculation', 'fitness', 'crossfit']
    cycling_keywords = ['vélo', 'bike', 'cycling', 'vtt', 'route', 'velo']
    trail_keywords = ['trail', 'trailrun', 'trail run', 'mountain', 'montagne', 'sentier']
    
    # Vérifier d'abord les mots-clés de trail (priorité haute)
    for keyword in trail_keywords:
        if keyword in name:
            if sport_type == 'run':
                return 'TrailRun'  # Trail running
            elif sport_type == 'ride':
                return 'Ride'  # Trail biking
    
    # Vérifier les mots-clés de raquette (priorité moyenne)
    for keyword in padel_keywords:
        if keyword in name:
            return 'RacketSport'
    
    # Vérifier les mots-clés de vélo (priorité moyenne)
    for keyword in cycling_keywords:
        if keyword in name:
            return 'Ride'
    
    # Vérifier les mots-clés de gym (priorité basse)
    for keyword in workout_keywords:
        if keyword in name:
            return 'Workout'
    
    # Détection par métriques - plus conservatrice
    distance = safe_get_value(activity_data, 'distance', 0)
    moving_time = safe_get_value(activity_data, 'moving_time', 0)
    
    # Seulement classer comme Workout si vraiment aucune distance ET temps court
    if distance == 0 and moving_time > 0 and moving_time < 300:  # Moins de 5 minutes
        return 'Workout'
    
    # Ne pas reclasser les activités de course avec distance > 50m
    if sport_type == 'run' and distance > 50:
        return 'Run'  # Garder Run pour les vraies courses
    
    # Gestion spécifique pour les activités de vélo
    if sport_type in ['ride', 'virtualride', 'ebikeride']:
        return 'Ride'
    
    # Gestion spécifique pour les trails
    if sport_type in ['trailrun', 'trail run']:
        return 'TrailRun'
    
    # Normaliser les types courants
    if sport_type == 'run':
        return 'Run'
    elif sport_type == 'swim':
        return 'Swim'
    elif sport_type == 'ride':
        return 'Ride'
    
    # Par défaut, garder le type original
    return sport_type or 'Unknown'

def insert_activity(conn: sqlite3.Connection, activity_data: dict) -> None:
    """Insère une activité dans la table activities."""
    try:
        # Vérifier que les données essentielles sont présentes
        if not activity_data or 'id' not in activity_data:
            logging.warning("Données d'activité invalides ou manquantes")
            return
            
        activity_id = activity_data['id']
        
        # Récupérer les données avec gestion des valeurs manquantes
        athlete = safe_get_value(activity_data, 'athlete', {})
        athlete_id = athlete.get('id', 0) if isinstance(athlete, dict) else 0
        
        # Détecter le vrai type d'activité
        real_sport_type = detect_real_activity_type(activity_data)
        original_sport_type = safe_get_value(activity_data, 'type', 'Unknown')
        
        if real_sport_type != original_sport_type:
            logging.info(f"🔄 Activité {activity_id}: {original_sport_type} → {real_sport_type}")
        
        # Vérifier si l'activité est privée (données minimales)
        is_private = (
            safe_get_value(activity_data, 'distance', 0) == 0 and
            safe_get_value(activity_data, 'moving_time', 0) == 0 and
            safe_get_value(activity_data, 'elapsed_time', 0) == 0
        )
        
        if is_private:
            logging.warning(f"⚠️  Activité {activity_id} détectée comme privée - données minimales")
        
        conn.execute("""
            INSERT OR REPLACE INTO activities (
                activity_id, fetched_at, athlete_id, name, distance_m, moving_time_s,
                elapsed_time_s, elev_gain_m, sport_type, workout_type, start_date_utc,
                start_date_local, timezone_label, utc_offset_s, visibility, trainer,
                commute, manual, private, gear_id, avg_speed_m_s, max_speed_m_s,
                avg_cadence_rpm, avg_watts, max_watts, weighted_avg_watts, kilojoules,
                has_heartrate, avg_heartrate_bpm, max_heartrate_bpm, calories_kcal,
                description, start_lat, start_lng, end_lat, end_lng, map_polyline,
                summary_polyline
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            activity_id,
            datetime.now().isoformat(),
            athlete_id,
            safe_get_value(activity_data, 'name', 'Activité privée'),
            safe_get_value(activity_data, 'distance', 0),
            safe_get_value(activity_data, 'moving_time', 0),
            safe_get_value(activity_data, 'elapsed_time', 0),
            safe_get_value(activity_data, 'total_elevation_gain', 0),
            real_sport_type,  # Utiliser le type détecté
            safe_get_value(activity_data, 'workout_type', None),
            safe_get_value(activity_data, 'start_date', None),
            safe_get_value(activity_data, 'start_date_local', None),
            safe_get_value(activity_data, 'timezone', None),
            safe_get_value(activity_data, 'utc_offset', None),
            safe_get_value(activity_data, 'visibility', 'private'),
            safe_get_value(activity_data, 'trainer', False),
            safe_get_value(activity_data, 'commute', False),
            safe_get_value(activity_data, 'manual', False),
            safe_get_value(activity_data, 'private', True),
            safe_get_value(activity_data, 'gear_id', None),
            safe_get_value(activity_data, 'average_speed', 0),
            safe_get_value(activity_data, 'max_speed', 0),
            safe_get_value(activity_data, 'average_cadence', 0),
            safe_get_value(activity_data, 'average_watts', 0),
            safe_get_value(activity_data, 'max_watts', 0),
            safe_get_value(activity_data, 'weighted_average_watts', 0),
            safe_get_value(activity_data, 'kilojoules', 0),
            safe_get_value(activity_data, 'has_heartrate', False),
            safe_get_value(activity_data, 'average_heartrate', 0),
            safe_get_value(activity_data, 'max_heartrate', 0),
            safe_get_value(activity_data, 'calories', 0),
            safe_get_value(activity_data, 'description', None),
            safe_get_list_item(safe_get_value(activity_data, 'start_latlng', []), 0),
            safe_get_list_item(safe_get_value(activity_data, 'start_latlng', []), 1),
            safe_get_list_item(safe_get_value(activity_data, 'end_latlng', []), 0),
            safe_get_list_item(safe_get_value(activity_data, 'end_latlng', []), 1),
            safe_get_value(activity_data, 'map', {}).get('polyline', None),
            safe_get_value(activity_data, 'map', {}).get('summary_polyline', None)
        ))
        
        activity_type_info = f" ({real_sport_type})" if real_sport_type != original_sport_type else ""
        logging.info(f"✅ Activité {activity_id} insérée" + (" (privée)" if is_private else "") + activity_type_info)
        
    except Exception as e:
        logging.error(f"❌ Erreur insertion activité {activity_id}: {e}")
        raise


def insert_laps(conn: sqlite3.Connection, activity_id: int, laps_data: list) -> None:
    """Insère les laps d'une activité avec gestion spéciale pour le vélo."""
    try:
        if not laps_data or len(laps_data) == 0:
            logging.debug(f"  → Aucun lap pour activité {activity_id}")
            return
            
        for i, lap in enumerate(laps_data):
            # Gestion défensive pour les laps de vélo qui peuvent avoir des structures différentes
            lap_id = safe_get_value(lap, 'id', i + 1)  # Utiliser l'index si pas d'ID
            lap_name = safe_get_value(lap, 'name', f'Lap {i + 1}')
            
            conn.execute("""
                INSERT OR REPLACE INTO laps (
                    activity_id, lap_id, name, distance_m, moving_time_s,
                    elapsed_time_s, elev_gain_m, start_index, end_index,
                    total_elevation_gain, average_speed, max_speed,
                    average_cadence, average_watts, max_watts, lap_index
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                activity_id,
                lap_id,
                lap_name,
                safe_get_value(lap, 'distance', 0),
                safe_get_value(lap, 'moving_time', 0),
                safe_get_value(lap, 'elapsed_time', 0),
                safe_get_value(lap, 'total_elevation_gain', 0),
                safe_get_value(lap, 'start_index', 0),
                safe_get_value(lap, 'end_index', 0),
                safe_get_value(lap, 'total_elevation_gain', 0),
                safe_get_value(lap, 'average_speed', 0),
                safe_get_value(lap, 'max_speed', 0),
                safe_get_value(lap, 'average_cadence', 0),
                safe_get_value(lap, 'average_watts', 0),
                safe_get_value(lap, 'max_watts', 0),
                i + 1  # lap_index basé sur la position
            ))
            
        logging.debug(f"  → {len(laps_data)} laps insérés")
        
    except Exception as e:
        logging.warning(f"  → Erreur insertion laps: {e}")
        # Ne pas faire échouer tout le traitement pour une erreur de laps

def insert_splits(conn: sqlite3.Connection, activity_id: int, activity_data: dict) -> None:
    """Insère les splits depuis les données d'activité avec gestion pour vélo."""
    try:
        # Splits métriques
        splits_metric = safe_get_value(activity_data, 'splits_metric', [])
        if splits_metric and len(splits_metric) > 0:
            for i, split in enumerate(splits_metric):
                split_id = safe_get_value(split, 'id', i + 1)  # Utiliser l'index si pas d'ID
                conn.execute("""
                    INSERT OR REPLACE INTO splits_metric (
                        activity_id, split_id, split_km, distance_m, elapsed_time_s,
                        moving_time_s, elevation_difference_m, average_speed_m_s
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    activity_id,
                    split_id,
                    i + 1,  # split_km = position dans la liste
                    safe_get_value(split, 'distance', 0),
                    safe_get_value(split, 'elapsed_time', 0),
                    safe_get_value(split, 'moving_time', 0),
                    safe_get_value(split, 'elevation_difference', 0),
                    safe_get_value(split, 'average_speed', 0)
                ))
        
        # Splits standard
        splits_standard = safe_get_value(activity_data, 'splits_standard', [])
        if splits_standard and len(splits_standard) > 0:
            for i, split in enumerate(splits_standard):
                split_id = safe_get_value(split, 'id', i + 1)  # Utiliser l'index si pas d'ID
                conn.execute("""
                    INSERT OR REPLACE INTO splits_standard (
                        activity_id, split_id, split_mile, distance_m, elapsed_time_s,
                        moving_time_s, elevation_difference_m, average_speed_m_s
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    activity_id,
                    split_id,
                    i + 1,  # split_mile = position dans la liste
                    safe_get_value(split, 'distance', 0),
                    safe_get_value(split, 'elapsed_time', 0),
                    safe_get_value(split, 'moving_time', 0),
                    safe_get_value(split, 'elevation_difference', 0),
                    safe_get_value(split, 'average_speed', 0)
                ))
                
        logging.debug(f"  → Splits insérés (metric: {len(splits_metric)}, standard: {len(splits_standard)})")
        
    except Exception as e:
        logging.warning(f"  → Erreur insertion splits: {e}")
        # Ne pas faire échouer tout le traitement pour une erreur de splits


def insert_segment_and_efforts(conn: sqlite3.Connection, activity_id: int, 
                             activity_data: Dict, token: str) -> None:
    """Insert/update segments et segment_efforts."""
    segment_efforts = activity_data.get("segment_efforts", [])
    
    for effort in segment_efforts:
        effort_id = effort.get("id")
        segment_data = effort.get("segment", {})
        segment_id = segment_data.get("id")
        
        if not segment_id:
            continue
            
        # Insert/update segment
        conn.execute(
            """
            INSERT OR REPLACE INTO segments (
                segment_id, name, activity_type, distance_m, avg_grade_pct,
                max_grade_pct, elev_high_m, elev_low_m, climb_category,
                city, state, country
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                segment_id,
                segment_data.get("name"),
                segment_data.get("activity_type"),
                segment_data.get("distance"),
                segment_data.get("average_grade"),
                segment_data.get("maximum_grade"),
                segment_data.get("elevation_high"),
                segment_data.get("elevation_low"),
                segment_data.get("climb_category"),
                segment_data.get("city"),
                segment_data.get("state"),
                segment_data.get("country"),
            ),
        )
        
        # Insert/update segment effort
        athlete_info = effort.get("athlete", {})
        athlete_id = athlete_info.get("id") if isinstance(athlete_info, dict) else None
        
        conn.execute(
            """
            INSERT OR REPLACE INTO segment_efforts (
                effort_id, activity_id, athlete_id, segment_id, name,
                elapsed_time_s, moving_time_s, start_date_utc, start_date_local,
                distance_m, average_cadence, average_watts, average_hr_bpm,
                max_hr_bpm, pr_rank
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                effort_id,
                activity_id,
                athlete_id,
                segment_id,
                effort.get("name"),
                effort.get("elapsed_time"),
                effort.get("moving_time"),
                effort.get("start_date"),
                effort.get("start_date_local"),
                effort.get("distance"),
                effort.get("average_cadence"),
                effort.get("average_watts"),
                effort.get("average_heartrate"),
                effort.get("max_heartrate"),
                effort.get("pr_rank"),
            ),
        )


def insert_best_efforts(conn: sqlite3.Connection, activity_id: int, activity_data: dict) -> None:
    """Insère les best efforts d'une activité."""
    try:
        best_efforts = safe_get_value(activity_data, 'best_efforts', [])
        if not best_efforts or len(best_efforts) == 0:
            logging.debug(f"  → Aucun best effort pour activité {activity_id}")
            return
            
        for effort in best_efforts:
            conn.execute("""
                INSERT OR REPLACE INTO best_efforts (
                    activity_id, effort_id, name, elapsed_time_s, moving_time_s,
                    start_date, start_date_local, distance_m, start_index,
                    end_index, pr_rank, achievements
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                activity_id,
                safe_get_value(effort, 'id', 0),
                safe_get_value(effort, 'name', 'Effort'),
                safe_get_value(effort, 'elapsed_time', 0),
                safe_get_value(effort, 'moving_time', 0),
                safe_get_value(effort, 'start_date', None),
                safe_get_value(effort, 'start_date_local', None),
                safe_get_value(effort, 'distance', 0),
                safe_get_value(effort, 'start_index', 0),
                safe_get_value(effort, 'end_index', 0),
                safe_get_value(effort, 'pr_rank', None),
                safe_get_value(effort, 'achievements', 0)
            ))
            
        logging.debug(f"  → {len(best_efforts)} best efforts insérés")
        
    except Exception as e:
        logging.warning(f"  → Erreur insertion best efforts: {e}")


def insert_streams(conn: sqlite3.Connection, activity_id: int, streams_data: Dict) -> None:
    """Insert/update activity streams."""
    for stream_type, stream_info in streams_data.items():
        if stream_info and "data" in stream_info:
            conn.execute(
                """
                INSERT OR REPLACE INTO activity_streams (activity_id, stream_type, data)
                VALUES (?, ?, ?)
                """,
                (
                    activity_id,
                    stream_type,
                    json.dumps(stream_info["data"]),
                ),
            )


def process_activity_complete(activity_id: int, token: str, detail_conn: sqlite3.Connection) -> None:
    """Traite complètement une activité avec tous ses détails."""
    logging.info(f"🏃 Traitement activité {activity_id}")
    
    try:
        # 1. Récupérer les détails principaux
        activity_data = fetch_activity_details(activity_id, token)
        
        # 2. Insérer athlete + activity
        insert_athlete(detail_conn, activity_data.get("athlete"))
        insert_activity(detail_conn, activity_data)
        
        # 3. Récupérer et insérer les laps
        try:
            laps_data = fetch_activity_laps(activity_id, token)
            insert_laps(detail_conn, activity_id, laps_data)
            logging.debug(f"  → {len(laps_data)} laps insérés")
        except Exception as e:
            logging.warning(f"  → Erreur laps: {e}")
        
        # 4. Insérer splits depuis les détails de l'activité
        insert_splits(detail_conn, activity_id, activity_data)
        
        # 5. Segments et efforts
        insert_segment_and_efforts(detail_conn, activity_id, activity_data, token)
        
        # 6. Best efforts
        insert_best_efforts(detail_conn, activity_id, activity_data)
        
        # 7. Récupérer et insérer les streams
        try:
            streams_data = fetch_activity_streams(activity_id, token)
            if streams_data:
                insert_streams(detail_conn, activity_id, streams_data)
                logging.debug(f"  → Streams: {list(streams_data.keys())}")
        except Exception as e:
            logging.warning(f"  → Erreur streams: {e}")
        
        # 8. Commit final
        detail_conn.commit()
        logging.info(f"✅ Activité {activity_id} traitée avec succès")
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.warning(f"⚠️  Activité {activity_id} non trouvée (404) - probablement supprimée ou inaccessible")
            # Ne pas re-traiter cette activité
            detail_conn.rollback()
            return
        elif e.response.status_code == 429:
            logging.error(f"🚫 Rate limit atteint pour activité {activity_id} - arrêt temporaire")
            detail_conn.rollback()
            raise  # Re-raise pour arrêter le traitement
        else:
            logging.error(f"❌ Erreur HTTP {e.response.status_code} pour activité {activity_id}: {e}")
            detail_conn.rollback()
            raise
    except Exception as e:
        logging.error(f"❌ Échec traitement activité {activity_id}: {e}")
        detail_conn.rollback()
        raise


# --- Boucle principale -----------------------------------------------------

def main(max_activities: int = None) -> None:
    """Fonction principale avec option de limiter le nombre d'activités"""
    logging.info(f"🏃‍♂️ Strava sync ETL démarré – intervalle {POLL_INTERVAL}s")
    if max_activities:
        logging.info(f"📊 Limite: {max_activities} activités maximum")
    
    activities_processed = 0
    
    while True:
        try:
            # Connexion BDD source + détection des nouvelles activités
            with sqlite3.connect(STRIDELTA_DB) as src_conn:
                ensure_processed_table(src_conn)
                new_ids = get_new_activity_ids(src_conn)
                
                if new_ids:
                    # Limiter le nombre d'activités si spécifié
                    if max_activities:
                        remaining = max_activities - activities_processed
                        if remaining <= 0:
                            logging.info(f"✅ Limite de {max_activities} activités atteinte")
                            break
                        new_ids = new_ids[:remaining]
                    
                    logging.info(f"📥 {len(new_ids)} activité(s) à synchroniser")
                    token = get_access_token()
                    
                    with sqlite3.connect(DETAIL_DB) as dst_conn:
                        for aid in new_ids:
                            try:
                                process_activity_complete(aid, token, dst_conn)
                                # Marquer comme traité seulement si succès
                                mark_as_processed(src_conn, aid)
                                activities_processed += 1
                                
                                # Vérifier la limite
                                if max_activities and activities_processed >= max_activities:
                                    logging.info(f"✅ Limite de {max_activities} activités atteinte")
                                    return
                                    
                            except requests.exceptions.HTTPError as e:
                                if e.response.status_code == 404:
                                    # Marquer les 404 comme traités pour éviter de les re-essayer
                                    logging.warning(f"🗑️  Activité {aid} marquée comme traitée (404)")
                                    mark_as_processed(src_conn, aid)
                                elif e.response.status_code == 429:
                                    logging.error(f"🚫 Rate limit atteint - pause de 15 minutes...")
                                    time.sleep(900)  # 15 minutes
                                    break  # Sortir de la boucle des activités
                                else:
                                    logging.error(f"❌ Erreur HTTP {e.response.status_code} pour {aid}: {e}")
                                    # Marquer comme traité pour éviter les boucles infinies sur erreurs persistantes
                                    mark_as_processed(src_conn, aid)
                            except sqlite3.Error as err:
                                logging.error(f"❌ Erreur SQL pour {aid}: {err}")
                                # Marquer comme traité pour éviter les boucles infinies
                                mark_as_processed(src_conn, aid)
                            except Exception as err:
                                logging.error(f"❌ Échec sync {aid}: {err}")
                                # Marquer comme traité pour éviter les boucles infinies
                                mark_as_processed(src_conn, aid)
                else:
                    logging.info("✅ Toutes les activités ont été traitées !")
                    logging.info("🛑 Arrêt automatique de l'ETL")
                    break  # Sortir de la boucle principale
                    
        except Exception as fatal:
            logging.exception(f"💥 Erreur fatale: {fatal}")
            break  # Arrêter en cas d'erreur fatale
            
        time.sleep(POLL_INTERVAL)
    
    logging.info(f"🏁 ETL terminé avec succès - {activities_processed} activités traitées")


if __name__ == "__main__":
    import argparse
    
    # Parser les arguments en ligne de commande
    parser = argparse.ArgumentParser(description="Script d'enrichissement des activités Strava")
    parser.add_argument("--max-activities", type=int, help="Nombre maximum d'activités à traiter")
    
    args = parser.parse_args()
    
    try:
        main(max_activities=args.max_activities)
    except KeyboardInterrupt:
        logging.info("👋 Arrêt demandé – à bientôt !")
