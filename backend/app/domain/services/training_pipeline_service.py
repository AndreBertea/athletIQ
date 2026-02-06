"""
Service d'intégration du pipeline de traitement des entraînements
Orchestre les modules de parsing, corrections et validation
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from uuid import UUID

from .training_parser import TrainingParser, ParsedTrainingSession
from .training_corrections import TrainingCorrections
from .training_validation import TrainingValidation
from ..entities.workout_plan import WorkoutPlan, WorkoutType, IntensityZone

logger = logging.getLogger(__name__)

class TrainingPipelineService:
    """Service principal pour le pipeline de traitement des entraînements"""
    
    def __init__(self):
        self.parser = TrainingParser()
        self.corrections = TrainingCorrections()
        self.validation = TrainingValidation()
    
    def process_google_calendar_events(self, events: List[Dict], user_id: UUID, session: Session) -> Dict[str, Any]:
        """Traite les événements Google Calendar et les enrichit avec le pipeline"""
        logger.info(f"Démarrage du traitement de {len(events)} événements Google Calendar")
        
        # ÉTAPE 1: Parsing des événements
        parsed_sessions = []
        for event in events:
            parsed_session = self.parser.parse_event(event)
            if parsed_session:
                parsed_sessions.append(parsed_session)
        
        logger.info(f"Parsing terminé: {len(parsed_sessions)} sessions parsées")
        
        # ÉTAPE 2: Corrections automatiques
        corrected_sessions = self.corrections.apply_corrections(parsed_sessions)
        
        # ÉTAPE 3: Validation
        validation_results = self.validation.validate_sessions(corrected_sessions)
        
        # ÉTAPE 4: Enrichissement des WorkoutPlan en base
        enriched_count = self._enrich_workout_plans(corrected_sessions, validation_results, user_id, session)
        
        # ÉTAPE 5: Génération du rapport final
        final_report = self._generate_integration_report(
            events, parsed_sessions, corrected_sessions, validation_results, enriched_count
        )
        
        logger.info("Traitement du pipeline terminé avec succès")
        return final_report
    
    def _enrich_workout_plans(self, sessions: List[ParsedTrainingSession], 
                            validation_results: Dict[str, Any], 
                            user_id: UUID, 
                            db_session: Session) -> int:
        """Enrichit les WorkoutPlan existants avec les données parsées"""
        enriched_count = 0
        
        for parsed_session in sessions:
            try:
                # Trouver le WorkoutPlan correspondant
                planned_date = datetime.fromisoformat(parsed_session.planned_date).date()
                workout_plan = db_session.exec(
                    select(WorkoutPlan).where(
                        WorkoutPlan.user_id == user_id,
                        WorkoutPlan.planned_date == planned_date,
                        WorkoutPlan.name == parsed_session.original_summary
                    )
                ).first()
                
                if workout_plan:
                    # Enrichir avec les données parsées
                    self._update_workout_plan_with_parsed_data(workout_plan, parsed_session, validation_results)
                    db_session.add(workout_plan)
                    enriched_count += 1
                    logger.info(f"WorkoutPlan enrichi: {workout_plan.name}")
                
            except Exception as e:
                logger.error(f"Erreur lors de l'enrichissement du WorkoutPlan: {e}")
                continue
        
        try:
            db_session.commit()
            logger.info(f"Enrichissement terminé: {enriched_count} WorkoutPlan mis à jour")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde: {e}")
            db_session.rollback()
        
        return enriched_count
    
    def _update_workout_plan_with_parsed_data(self, workout_plan: WorkoutPlan, 
                                            parsed_session: ParsedTrainingSession,
                                            validation_results: Dict[str, Any]):
        """Met à jour un WorkoutPlan avec les données parsées"""
        # Mapper le type parsé vers l'enum WorkoutType
        workout_plan.parsed_type = parsed_session.type
        if parsed_session.type:
            workout_plan.workout_type = self._map_parsed_type_to_enum(parsed_session.type)
        
        # Mapper l'intensité parsée vers l'enum IntensityZone
        workout_plan.parsed_intensity = parsed_session.intensity
        if parsed_session.intensity:
            workout_plan.intensity_zone = self._map_parsed_intensity_to_enum(parsed_session.intensity)
        
        # Données estimées
        workout_plan.parsed_estimated_distance = parsed_session.estimated_distance_km
        workout_plan.parsed_estimated_pace = parsed_session.estimated_pace_min_km
        workout_plan.parsed_estimated_heart_rate = parsed_session.estimated_heart_rate
        workout_plan.parsed_confidence_score = parsed_session.confidence_score
        
        # Structure détaillée
        workout_plan.parsed_main_sets = parsed_session.main_sets
        workout_plan.parsed_warmup = parsed_session.warmup
        workout_plan.parsed_cooldown = parsed_session.cooldown
        
        # Métadonnées du parsing
        workout_plan.parsing_corrections = parsed_session.corrections
        workout_plan.parsed_at = datetime.now()
        
        # Trouver les problèmes de validation pour cette session
        session_validation = next(
            (sv for sv in validation_results['sessions_validation'] 
             if sv['session_summary'] == parsed_session.original_summary and 
                sv['session_date'] == parsed_session.planned_date),
            None
        )
        
        if session_validation:
            workout_plan.parsing_validation_issues = session_validation['issues']
            workout_plan.parsing_validation_score = session_validation['validation_score']
        
        # Mettre à jour les champs principaux si ils sont vides
        if not workout_plan.planned_distance and parsed_session.estimated_distance_km:
            workout_plan.planned_distance = parsed_session.estimated_distance_km
        
        if not workout_plan.planned_duration and parsed_session.duration_minutes:
            workout_plan.planned_duration = parsed_session.duration_minutes * 60  # Convertir en secondes
        
        if not workout_plan.description and parsed_session.original_description:
            workout_plan.description = parsed_session.original_description
    
    def _map_parsed_type_to_enum(self, parsed_type: str) -> WorkoutType:
        """Mappe le type parsé vers l'enum WorkoutType"""
        mapping = {
            'Endurance': WorkoutType.EASY_RUN,  # Endurance = course facile
            'Seuil': WorkoutType.TEMPO,         # Seuil = tempo
            'Intervalle': WorkoutType.INTERVAL,
            'Allure': WorkoutType.TEMPO,        # Allure = tempo
            'Pyramide': WorkoutType.INTERVAL,   # Pyramide = intervalle
            'Salle': WorkoutType.RECOVERY,      # Salle = récupération
            'Rando': WorkoutType.LONG_RUN,      # Rando = long run
            'Fartlek': WorkoutType.FARTLEK,
            'Course': WorkoutType.RACE
        }
        return mapping.get(parsed_type, WorkoutType.EASY_RUN)
    
    def _map_parsed_intensity_to_enum(self, parsed_intensity: str) -> IntensityZone:
        """Mappe l'intensité parsée vers l'enum IntensityZone"""
        mapping = {
            'Faible': IntensityZone.ZONE_1,     # Faible = zone 1
            'Modérée': IntensityZone.ZONE_2,    # Modérée = zone 2
            'Élevée': IntensityZone.ZONE_4      # Élevée = zone 4 (seuil)
        }
        return mapping.get(parsed_intensity, IntensityZone.ZONE_2)
    
    def _generate_integration_report(self, events: List[Dict], 
                                   parsed_sessions: List[ParsedTrainingSession],
                                   corrected_sessions: List[ParsedTrainingSession],
                                   validation_results: Dict[str, Any],
                                   enriched_count: int) -> Dict[str, Any]:
        """Génère un rapport complet d'intégration"""
        corrections_summary = self.corrections.get_corrections_summary()
        
        report = {
            'pipeline_execution': {
                'total_events_processed': len(events),
                'sessions_parsed': len(parsed_sessions),
                'sessions_corrected': len(corrected_sessions),
                'workout_plans_enriched': enriched_count
            },
            'parsing_results': {
                'confidence_scores': {
                    'average': sum(s.confidence_score or 0 for s in parsed_sessions) / len(parsed_sessions) if parsed_sessions else 0,
                    'min': min(s.confidence_score or 0 for s in parsed_sessions) if parsed_sessions else 0,
                    'max': max(s.confidence_score or 0 for s in parsed_sessions) if parsed_sessions else 0
                },
                'types_detected': self._count_types_detected(parsed_sessions),
                'intensities_detected': self._count_intensities_detected(parsed_sessions)
            },
            'corrections_applied': corrections_summary,
            'validation_results': validation_results,
            'execution_timestamp': datetime.now().isoformat()
        }
        
        return report
    
    def _count_types_detected(self, sessions: List[ParsedTrainingSession]) -> Dict[str, int]:
        """Compte les types d'entraînement détectés"""
        counts = {}
        for session in sessions:
            if session.type:
                counts[session.type] = counts.get(session.type, 0) + 1
        return counts
    
    def _count_intensities_detected(self, sessions: List[ParsedTrainingSession]) -> Dict[str, int]:
        """Compte les intensités détectées"""
        counts = {}
        for session in sessions:
            if session.intensity:
                counts[session.intensity] = counts.get(session.intensity, 0) + 1
        return counts
    
    def get_parsing_statistics(self, user_id: UUID, session: Session) -> Dict[str, Any]:
        """Récupère les statistiques de parsing pour un utilisateur"""
        workout_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.user_id == user_id)
        ).all()
        
        parsed_plans = [wp for wp in workout_plans if wp.parsed_at is not None]
        
        if not parsed_plans:
            return {
                'total_workout_plans': len(workout_plans),
                'parsed_workout_plans': 0,
                'parsing_rate': 0.0,
                'average_confidence': 0.0,
                'average_validation_score': 0.0
            }
        
        return {
            'total_workout_plans': len(workout_plans),
            'parsed_workout_plans': len(parsed_plans),
            'parsing_rate': len(parsed_plans) / len(workout_plans),
            'average_confidence': sum(wp.parsed_confidence_score or 0 for wp in parsed_plans) / len(parsed_plans),
            'average_validation_score': sum(wp.parsing_validation_score or 0 for wp in parsed_plans) / len(parsed_plans),
            'types_distribution': self._count_workout_plan_types(parsed_plans),
            'intensities_distribution': self._count_workout_plan_intensities(parsed_plans)
        }
    
    def _count_workout_plan_types(self, workout_plans: List[WorkoutPlan]) -> Dict[str, int]:
        """Compte les types d'entraînement dans les WorkoutPlan"""
        counts = {}
        for wp in workout_plans:
            if wp.parsed_type:
                counts[wp.parsed_type] = counts.get(wp.parsed_type, 0) + 1
        return counts
    
    def _count_workout_plan_intensities(self, workout_plans: List[WorkoutPlan]) -> Dict[str, int]:
        """Compte les intensités dans les WorkoutPlan"""
        counts = {}
        for wp in workout_plans:
            if wp.parsed_intensity:
                counts[wp.parsed_intensity] = counts.get(wp.parsed_intensity, 0) + 1
        return counts 