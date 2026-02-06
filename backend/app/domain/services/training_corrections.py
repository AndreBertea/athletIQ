"""
Module de corrections automatiques des sessions d'entraînement
Utilise la logique centralisée du parser pour éviter les duplications
"""
import logging
from typing import List, Dict, Optional
from .training_parser import ParsedTrainingSession, INTENSITY_PACES, DEFAULT_PACE

logger = logging.getLogger(__name__)

class TrainingCorrections:
    """Service de corrections automatiques pour les sessions d'entraînement"""
    
    def __init__(self):
        self.corrections_applied = []
    
    def apply_corrections(self, sessions: List[ParsedTrainingSession]) -> List[ParsedTrainingSession]:
        """Applique toutes les corrections automatiques aux sessions"""
        corrected_sessions = []
        
        for session in sessions:
            corrections = []
            
            # Correction de l'intensité
            if self._has_inconsistent_intensity(session):
                if self._fix_intensity_consistency(session):
                    corrections.append("Intensité corrigée automatiquement")
            
            # Correction de la distance
            if self._has_inconsistent_distance(session):
                if self._fix_distance_estimation(session):
                    corrections.append("Distance estimée corrigée")
            
            # Correction des séries manquantes
            if self._has_missing_main_sets(session):
                if self._fix_missing_main_sets(session):
                    corrections.append("Séries principales ajoutées")
            
            # Mise à jour des corrections appliquées
            if corrections:
                session.corrections = corrections
                self.corrections_applied.extend(corrections)
            
            corrected_sessions.append(session)
        
        logger.info(f"Corrections appliquées: {len(self.corrections_applied)}")
        return corrected_sessions
    
    def _has_inconsistent_intensity(self, session: ParsedTrainingSession) -> bool:
        """Vérifie si l'intensité est incohérente avec les allures mentionnées"""
        if not session.intensity or not session.estimated_pace_min_km:
            return False
        
        text = f"{session.original_summary} {session.original_description}"
        
        # Vérifier si l'intensité actuelle correspond aux allures détectées
        for intensity, paces in INTENSITY_PACES.items():
            if any(pace in text for pace in paces):
                return session.intensity != intensity
        
        return False
    
    def _fix_intensity_consistency(self, session: ParsedTrainingSession) -> bool:
        """Corrige l'intensité pour qu'elle soit cohérente avec les allures"""
        text = f"{session.original_summary} {session.original_description}"
        
        for intensity, paces in INTENSITY_PACES.items():
            if any(pace in text for pace in paces):
                old_intensity = session.intensity
                session.intensity = intensity
                logger.info(f"Intensité corrigée: {old_intensity} -> {intensity}")
                return True
        
        return False
    
    def _has_inconsistent_distance(self, session: ParsedTrainingSession) -> bool:
        """Vérifie si la distance estimée est incohérente"""
        if not session.estimated_distance_km or not session.duration_minutes:
            return False
        
        # Calculer la distance attendue basée sur la durée
        expected_distance = session.duration_minutes / DEFAULT_PACE
        
        # Tolérance de 20% pour les variations
        tolerance = expected_distance * 0.2
        min_expected = expected_distance - tolerance
        max_expected = expected_distance + tolerance
        
        return not (min_expected <= session.estimated_distance_km <= max_expected)
    
    def _fix_distance_estimation(self, session: ParsedTrainingSession) -> bool:
        """Corrige l'estimation de distance"""
        if not session.duration_minutes:
            return False
        
        old_distance = session.estimated_distance_km
        session.estimated_distance_km = session.duration_minutes / DEFAULT_PACE
        
        logger.info(f"Distance corrigée: {old_distance} -> {session.estimated_distance_km}")
        return True
    
    def _has_missing_main_sets(self, session: ParsedTrainingSession) -> bool:
        """Vérifie si les séries principales sont manquantes"""
        if not session.main_sets:
            return True
        
        # Vérifier si le type d'entraînement suggère des séries spécifiques
        text = f"{session.original_summary} {session.original_description}"
        
        if session.type == 'Intervalle' and not any('intervalle' in str(ms) for ms in session.main_sets):
            return True
        
        if session.type == 'Seuil' and not any('seuil' in str(ms) for ms in session.main_sets):
            return True
        
        return False
    
    def _fix_missing_main_sets(self, session: ParsedTrainingSession) -> bool:
        """Ajoute des séries principales manquantes basées sur le type d'entraînement"""
        if not session.main_sets:
            session.main_sets = []
        
        text = f"{session.original_summary} {session.original_description}"
        
        # Ajouter des séries basées sur le type d'entraînement
        if session.type == 'Intervalle':
            # Chercher un pattern d'intervalle dans le texte
            import re
            interval_match = re.search(r'(\d+)x(\d+)min', text)
            if interval_match:
                reps = int(interval_match.group(1))
                duration = int(interval_match.group(2))
                
                session.main_sets.append({
                    'type': 'intervalle',
                    'repetitions': reps,
                    'duration_minutes': duration,
                    'recovery': f"{DEFAULT_PACE}min",
                    'total_duration': reps * duration + (reps - 1) * DEFAULT_PACE
                })
                return True
        
        elif session.type == 'Seuil':
            # Ajouter un bloc de seuil par défaut
            session.main_sets.append({
                'type': 'seuil',
                'duration_minutes': session.duration_minutes,
                'repetitions': 1
            })
            return True
        
        return False
    
    def get_corrections_summary(self) -> Dict:
        """Retourne un résumé des corrections appliquées"""
        return {
            'total_corrections': len(self.corrections_applied),
            'corrections_by_type': self._count_corrections_by_type(),
            'corrections_applied': self.corrections_applied
        }
    
    def _count_corrections_by_type(self) -> Dict[str, int]:
        """Compte les corrections par type"""
        counts = {}
        for correction in self.corrections_applied:
            if 'intensité' in correction.lower():
                counts['intensity'] = counts.get('intensity', 0) + 1
            elif 'distance' in correction.lower():
                counts['distance'] = counts.get('distance', 0) + 1
            elif 'séries' in correction.lower():
                counts['main_sets'] = counts.get('main_sets', 0) + 1
            else:
                counts['other'] = counts.get('other', 0) + 1
        return counts 