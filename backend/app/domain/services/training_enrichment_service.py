"""
Service d'enrichissement des WorkoutPlan utilisant le pipeline existant
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlmodel import select

# Ajouter le répertoire backend au path pour importer le pipeline
backend_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_dir))

from training_pipeline import TrainingPipeline, TrainingSession
from app.domain.entities.workout_plan import WorkoutPlan, WorkoutType, IntensityZone


class TrainingEnrichmentService:
    """Service d'enrichissement des WorkoutPlan avec le pipeline existant"""
    
    def __init__(self):
        self.pipeline = TrainingPipeline()
    
    def enrich_workout_plans_from_events(self, events: List[Dict], user_id: UUID, db_session: Session) -> Dict[str, Any]:
        """Enrichit les WorkoutPlan avec les données parsées du pipeline existant"""
        
        # 1. Créer un fichier temporaire avec les événements
        temp_file = self._create_temp_events_file(events)
        
        try:
            # 2. Utiliser le pipeline existant pour parser
            self.pipeline.input_file = temp_file
            sessions = self.pipeline.parse_events()
            
            # 3. Appliquer les corrections
            self.pipeline.apply_corrections(sessions)
            
            # 4. Valider
            validation_results = self.pipeline.validate_sessions(sessions)
            
            # 5. Enrichir les WorkoutPlan en base
            enriched_count = self._enrich_workout_plans(sessions, validation_results, user_id, db_session)
            
            # 6. Générer le rapport
            return self._generate_enrichment_report(events, sessions, validation_results, enriched_count)
            
        finally:
            # Nettoyer le fichier temporaire
            if temp_file.exists():
                temp_file.unlink()
    
    def _create_temp_events_file(self, events: List[Dict]) -> Path:
        """Crée un fichier temporaire avec les événements pour le pipeline"""
        temp_file = Path("temp_events.json")
        
        data = {
            "import_info": {
                "import_date": "2025-07-28T00:00:00",
                "total_events_imported": len(events)
            },
            "imported_events": events
        }
        
        import json
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return temp_file
    
    def _enrich_workout_plans(self, sessions: List[TrainingSession], validation_results: Dict, user_id: UUID, db_session: Session) -> int:
        """Enrichit les WorkoutPlan avec les données parsées"""
        enriched_count = 0
        
        for session in sessions:
            # Trouver le WorkoutPlan correspondant
            workout_plan = self._find_matching_workout_plan(session, user_id, db_session)
            
            if workout_plan:
                # Enrichir avec les données parsées
                self._update_workout_plan_with_session(workout_plan, session, validation_results)
                db_session.commit()
                enriched_count += 1
        
        return enriched_count
    
    def _find_matching_workout_plan(self, session: TrainingSession, user_id: UUID, db_session: Session) -> Optional[WorkoutPlan]:
        """Trouve le WorkoutPlan correspondant à une session parsée"""
        # Extraire la date de la session
        from datetime import datetime
        try:
            session_date = datetime.fromisoformat(session.planned_date.replace('Z', '+00:00')).date()
        except:
            return None
        
        # Chercher le WorkoutPlan par date et nom
        stmt = select(WorkoutPlan).where(
            WorkoutPlan.user_id == str(user_id),
            WorkoutPlan.planned_date == session_date
        )
        
        workout_plans = db_session.exec(stmt).all()
        
        # Trouver le plus proche par nom
        best_match = None
        best_score = 0
        
        for wp in workout_plans:
            score = self._calculate_name_similarity(wp.name, session.original_summary)
            if score > best_score:
                best_score = score
                best_match = wp
        
        return best_match if best_score > 0.3 else None
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calcule la similarité entre deux noms"""
        # Simplification : compter les mots communs
        words1 = set(name1.lower().split())
        words2 = set(name2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def _update_workout_plan_with_session(self, workout_plan: WorkoutPlan, session: TrainingSession, validation_results: Dict):
        """Met à jour un WorkoutPlan avec les données parsées"""
        
        # Mapper les données parsées
        workout_plan.parsed_type = session.type
        workout_plan.parsed_intensity = session.intensity
        workout_plan.parsed_estimated_distance = session.estimated_distance_km
        workout_plan.parsed_estimated_pace = session.estimated_pace_min_km
        workout_plan.parsed_estimated_heart_rate = session.estimated_heart_rate
        workout_plan.parsed_confidence_score = session.confidence_score
        workout_plan.parsed_main_sets = session.main_sets
        workout_plan.parsed_warmup = session.warmup
        workout_plan.parsed_cooldown = session.cooldown
        workout_plan.parsing_corrections = session.corrections
        
        # Trouver les problèmes de validation pour cette session
        session_issues = []
        for result in validation_results.get('detailed_results', []):
            if result.get('summary') == session.original_summary:
                session_issues = result.get('issues', [])
                break
        
        workout_plan.parsing_validation_issues = session_issues
        workout_plan.parsing_validation_score = self._calculate_validation_score(session_issues)
        
        # Mettre à jour les champs principaux si ils sont vides ou par défaut
        if workout_plan.workout_type == WorkoutType.EASY_RUN:
            workout_plan.workout_type = self._map_parsed_type_to_enum(session.type)
        
        if workout_plan.planned_distance == 0.0 and session.estimated_distance_km:
            workout_plan.planned_distance = session.estimated_distance_km
        
        if workout_plan.planned_pace == 0.0 and session.estimated_pace_min_km:
            # Convertir l'allure en format numérique
            pace_value = self._convert_pace_to_float(session.estimated_pace_min_km)
            if pace_value:
                workout_plan.planned_pace = pace_value
        
        if workout_plan.intensity_zone is None:
            workout_plan.intensity_zone = self._map_parsed_intensity_to_enum(session.intensity)
        
        # Marquer comme parsé
        from datetime import datetime
        workout_plan.parsed_at = datetime.now()
    
    def _map_parsed_type_to_enum(self, parsed_type: str) -> WorkoutType:
        """Mappe le type parsé vers l'enum WorkoutType"""
        mapping = {
            'Endurance': WorkoutType.EASY_RUN,
            'Seuil': WorkoutType.THRESHOLD,
            'Allure': WorkoutType.TEMPO,
            'Pyramide': WorkoutType.INTERVALS,
            'Musculation': WorkoutType.STRENGTH,
            'Rando-Course': WorkoutType.LONG_RUN,
            'Randonnée': WorkoutType.LONG_RUN,
            'Veille de course': WorkoutType.EASY_RUN
        }
        return mapping.get(parsed_type, WorkoutType.EASY_RUN)
    
    def _map_parsed_intensity_to_enum(self, parsed_intensity: str) -> IntensityZone:
        """Mappe l'intensité parsée vers l'enum IntensityZone"""
        mapping = {
            'Faible': IntensityZone.EASY,
            'Modérée': IntensityZone.MODERATE,
            'Élevée': IntensityZone.HARD
        }
        return mapping.get(parsed_intensity, IntensityZone.MODERATE)
    
    def _convert_pace_to_float(self, pace_str: str) -> Optional[float]:
        """Convertit une allure mm:ss/km en float"""
        import re
        match = re.search(r'(\d+):(\d+)', pace_str)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            return minutes + seconds / 60.0
        return None
    
    def _calculate_validation_score(self, issues: List[str]) -> float:
        """Calcule un score de validation basé sur les problèmes"""
        if not issues:
            return 1.0
        
        # Score de base avec pénalités
        score = 1.0
        for issue in issues:
            if 'type' in issue.lower():
                score -= 0.2
            elif 'intensité' in issue.lower():
                score -= 0.15
            elif 'main_sets' in issue.lower():
                score -= 0.25
            elif 'distance' in issue.lower():
                score -= 0.1
        
        return max(0.0, score)
    
    def _generate_enrichment_report(self, events: List[Dict], sessions: List[TrainingSession], validation_results: Dict, enriched_count: int) -> Dict[str, Any]:
        """Génère un rapport d'enrichissement"""
        return {
            "enrichment_summary": {
                "total_events": len(events),
                "sessions_parsed": len(sessions),
                "workout_plans_enriched": enriched_count,
                "enrichment_rate": round(enriched_count / len(events) * 100, 1) if events else 0
            },
            "parsing_results": {
                "confidence_scores": {
                    "average": round(sum(s.confidence_score or 0 for s in sessions) / len(sessions), 2) if sessions else 0,
                    "min": min((s.confidence_score or 0 for s in sessions), default=0),
                    "max": max((s.confidence_score or 0 for s in sessions), default=0)
                },
                "types_detected": self._count_types(sessions),
                "intensities_detected": self._count_intensities(sessions)
            },
            "validation_results": {
                "total_sessions": validation_results.get('total_sessions', 0),
                "sessions_with_issues": validation_results.get('sessions_with_issues', 0),
                "total_issues": validation_results.get('total_issues', 0),
                "issue_types": validation_results.get('issue_types', {})
            },
            "corrections_applied": {
                "total_corrections": sum(len(s.corrections or []) for s in sessions),
                "sessions_corrected": sum(1 for s in sessions if s.corrections)
            }
        }
    
    def _count_types(self, sessions: List[TrainingSession]) -> Dict[str, int]:
        """Compte les types détectés"""
        counts = {}
        for session in sessions:
            if session.type:
                counts[session.type] = counts.get(session.type, 0) + 1
        return counts
    
    def _count_intensities(self, sessions: List[TrainingSession]) -> Dict[str, int]:
        """Compte les intensités détectées"""
        counts = {}
        for session in sessions:
            if session.intensity:
                counts[session.intensity] = counts.get(session.intensity, 0) + 1
        return counts 