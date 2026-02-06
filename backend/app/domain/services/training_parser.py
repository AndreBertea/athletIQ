"""
Module de parsing des sessions d'entraînement
Centralise la logique d'extraction des types, intensités et structures d'entraînement
"""
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

# ============ CONSTANTES ET CONFIGURATION ============

# Types d'entraînement reconnus
TRAINING_TYPES = {
    'endurance': ['endurance', 'fond', 'base', 'récupération'],
    'seuil': ['seuil', 'threshold', 'lactique'],
    'intervalle': ['intervalle', 'fractionné', 'vma', 'vo2max'],
    'allure': ['allure', 'tempo', 'rythme'],
    'pyramide': ['pyramide', 'pyramid'],
    'fartlek': ['fartlek'],
    'course': ['course', 'compétition', 'race'],
    'salle': ['salle', 'musculation', 'gym'],
    'rando': ['rando', 'randonnée', 'trail']
}

# Allures de référence pour l'intensité (min/km)
INTENSITY_PACES = {
    'Élevée': ['4:19', '4:30', '4:45'],
    'Modérée': ['5:00', '5:15', '5:30'],
    'Faible': ['6:00', '6:30', '7:00']
}

# Vitesse moyenne par défaut pour estimation distance (min/km)
DEFAULT_PACE = 6.5

# Durée de récupération par défaut (minutes)
DEFAULT_RECOVERY_TIME = 2

# Plages de fréquence cardiaque par intensité (bpm)
HEART_RATE_RANGES = {
    'Élevée': '160-180',
    'Modérée': '140-160', 
    'Faible': '120-140'
}

@dataclass
class ParsedTrainingSession:
    """Structure de données pour une session parsée"""
    original_summary: str
    original_description: str
    planned_date: str
    duration_minutes: int
    is_completed: bool
    source: str
    
    # Données extraites
    type: Optional[str] = None
    intensity: Optional[str] = None
    warmup: Optional[str] = None
    main_sets: Optional[List[Dict]] = None
    cooldown: Optional[str] = None
    estimated_distance_km: Optional[float] = None
    estimated_pace_min_km: Optional[str] = None
    estimated_heart_rate: Optional[str] = None
    confidence_score: Optional[float] = None
    processed_at: Optional[str] = None
    corrections: Optional[List[str]] = None

class TrainingParser:
    """Parser centralisé pour les sessions d'entraînement"""
    
    def __init__(self):
        self.corrections_applied = []
    
    def parse_event(self, event: Dict) -> Optional[ParsedTrainingSession]:
        """Parse un événement Google Calendar en session d'entraînement structurée"""
        try:
            # Extraction des données de base
            summary = event.get('summary', '')
            description = event.get('description', '')
            planned_date = event.get('planned_date', '')
            duration_minutes = event.get('duration_minutes', 60)
            is_completed = event.get('is_completed', False)
            source = event.get('source', 'google_calendar')
            
            # Création de la session de base
            session = ParsedTrainingSession(
                original_summary=summary,
                original_description=description,
                planned_date=planned_date,
                duration_minutes=duration_minutes,
                is_completed=is_completed,
                source=source,
                processed_at=datetime.now().isoformat(),
                corrections=[]
            )
            
            # Extraction des données structurées
            session.type = self._extract_training_type(summary, description)
            session.intensity = self._extract_intensity(summary, description)
            session.estimated_distance_km = self._estimate_distance(summary, description, duration_minutes)
            session.estimated_pace_min_km = self._extract_pace(description)
            session.estimated_heart_rate = self._extract_heart_rate(description)
            
            # Extraction de la structure d'entraînement
            structure = self._extract_structure(summary, description, duration_minutes)
            session.main_sets = structure.get('main_sets', [])
            session.warmup = structure.get('warmup')
            session.cooldown = structure.get('cooldown')
            
            # Calcul du score de confiance
            session.confidence_score = self._calculate_confidence_score(session)
            
            return session
            
        except Exception as e:
            logger.error(f"Erreur lors du parsing de l'événement {event.get('summary', 'Sans titre')}: {e}")
            return None
    
    def _extract_training_type(self, summary: str, description: str) -> str:
        """Extrait le type d'entraînement depuis le résumé et la description"""
        text = f"{summary} {description}".lower()
        
        for training_type, keywords in TRAINING_TYPES.items():
            if any(keyword in text for keyword in keywords):
                return training_type.capitalize()
        
        # Fallback basé sur des patterns spécifiques
        if re.search(r'\d+x\d+min', text):
            return 'Intervalle'
        elif re.search(r'\d+km', text):
            return 'Allure'
        elif 'seuil' in text:
            return 'Seuil'
        
        return 'Endurance'  # Type par défaut
    
    def _extract_intensity(self, summary: str, description: str) -> str:
        """Extrait l'intensité basée sur les allures mentionnées"""
        text = f"{summary} {description}"
        
        for intensity, paces in INTENSITY_PACES.items():
            if any(pace in text for pace in paces):
                return intensity
        
        # Fallback basé sur le type d'entraînement
        training_type = self._extract_training_type(summary, description)
        if training_type in ['Intervalle', 'Seuil']:
            return 'Élevée'
        elif training_type in ['Allure', 'Pyramide']:
            return 'Modérée'
        else:
            return 'Faible'
    
    def _extract_structure(self, summary: str, description: str, duration_minutes: int) -> Dict:
        """Extrait la structure détaillée de l'entraînement"""
        text = f"{summary} {description}"
        main_sets = []
        
        # Pattern pour les intervalles répétitifs (ex: 4x4min en 5:03/km)
        interval_pattern = r'(\d+)x(\d+)min(?:\s+en\s+([^,\n]+))?(?:\s*,\s*(\d+)min\s+récup)?'
        interval_matches = re.finditer(interval_pattern, text)
        
        for match in interval_matches:
            reps = int(match.group(1))
            duration = int(match.group(2))
            pace = match.group(3) if match.group(3) else None
            recovery = match.group(4) if match.group(4) else f"{DEFAULT_RECOVERY_TIME}min"
            
            main_sets.append({
                'type': 'intervalle',
                'repetitions': reps,
                'duration_minutes': duration,
                'pace': pace,
                'recovery': recovery,
                'total_duration': reps * duration + (reps - 1) * int(recovery.replace('min', ''))
            })
        
        # Pattern pour les blocs simples (ex: 5min en 5:30/km)
        # Éviter les doublons avec les intervalles déjà détectés
        simple_pattern = r'(?<!x)(\d+)min(?:\s+en\s+([^,\n]+))?'
        simple_matches = re.finditer(simple_pattern, text)
        
        for match in simple_matches:
            duration = int(match.group(1))
            pace = match.group(2) if match.group(2) else None
            
            # Vérifier que ce bloc n'est pas déjà capturé par un intervalle
            is_duplicate = any(
                set_item.get('duration_minutes') == duration and 
                set_item.get('type') == 'intervalle'
                for set_item in main_sets
            )
            
            if not is_duplicate:
                main_sets.append({
                    'type': 'bloc',
                    'duration_minutes': duration,
                    'pace': pace,
                    'repetitions': 1
                })
        
        # Détection des pyramides (seulement si explicitement mentionné)
        if 'pyramide' in text.lower():
            pyramid_pattern = r'(\d+)min(?:\s*\+\s*)?'
            pyramid_matches = re.findall(pyramid_pattern, text)
            
            for duration_str in pyramid_matches:
                duration = int(duration_str)
                main_sets.append({
                    'type': 'pyramide',
                    'duration_minutes': duration,
                    'repetitions': 1
                })
        
        # Si aucune structure détectée, créer un bloc par défaut
        if not main_sets:
            main_sets.append({
                'type': 'endurance',
                'duration_minutes': duration_minutes,
                'repetitions': 1
            })
        
        return {
            'main_sets': main_sets,
            'warmup': None,  # À implémenter si nécessaire
            'cooldown': None  # À implémenter si nécessaire
        }
    
    def _estimate_distance(self, summary: str, description: str, duration_minutes: int) -> Optional[float]:
        """Estime la distance basée sur la description ou la durée"""
        text = f"{summary} {description}"
        
        # Recherche de distance explicite
        distance_match = re.search(r'(\d+(?:,\d+)?)\s*km', text)
        if distance_match:
            return float(distance_match.group(1).replace(',', '.'))
        
        # Estimation basée sur la durée et le type d'entraînement
        training_type = self._extract_training_type(summary, description)
        
        if training_type == 'Intervalle':
            # Pour les intervalles, estimer la distance des fractions
            interval_match = re.search(r'(\d+)x(\d+)min', text)
            if interval_match:
                reps = int(interval_match.group(1))
                duration = int(interval_match.group(2))
                # Estimation: 1km par 5min d'effort
                estimated_km_per_interval = duration / 5.0
                return reps * estimated_km_per_interval
        
        # Estimation générale basée sur la durée
        # Vitesse moyenne de 6.5 min/km par défaut
        return duration_minutes / DEFAULT_PACE
    
    def _extract_pace(self, description: str) -> Optional[str]:
        """Extrait l'allure mentionnée dans la description"""
        pace_match = re.search(r'(\d+:\d+)(?:\s*/\s*km)?', description)
        return pace_match.group(1) if pace_match else None
    
    def _extract_heart_rate(self, description: str) -> Optional[str]:
        """Extrait la fréquence cardiaque mentionnée"""
        hr_match = re.search(r'(\d+)(?:\s*-\s*(\d+))?\s*bpm', description)
        if hr_match:
            if hr_match.group(2):
                return f"{hr_match.group(1)}-{hr_match.group(2)}bpm"
            else:
                return f"{hr_match.group(1)}bpm"
        
        # Fallback basé sur l'intensité
        return None
    
    def _calculate_confidence_score(self, session: ParsedTrainingSession) -> float:
        """Calcule un score de confiance pour le parsing"""
        score = 0.5  # Score de base
        
        # Bonus pour les éléments bien détectés
        if session.type and session.type != 'Endurance':
            score += 0.2
        if session.intensity and session.intensity != 'Faible':
            score += 0.1
        if session.estimated_pace_min_km:
            score += 0.1
        if session.main_sets and len(session.main_sets) > 0:
            score += 0.1
        
        return min(score, 1.0)  # Maximum 1.0 