"""
Module de validation des sessions d'entraînement
Utilise la logique centralisée du parser pour éviter les duplications
"""
import logging
from typing import List, Dict, Any
from .training_parser import ParsedTrainingSession, INTENSITY_PACES

logger = logging.getLogger(__name__)

class TrainingValidation:
    """Service de validation des sessions d'entraînement"""
    
    def __init__(self):
        self.validation_issues = []
    
    def validate_sessions(self, sessions: List[ParsedTrainingSession]) -> Dict[str, Any]:
        """Valide toutes les sessions et génère un rapport détaillé"""
        validation_results = {
            'total_sessions': len(sessions),
            'valid_sessions': 0,
            'sessions_with_issues': 0,
            'total_issues': 0,
            'issues_by_category': {},
            'sessions_validation': []
        }
        
        for session in sessions:
            session_issues = self._validate_single_session(session)
            
            if session_issues:
                validation_results['sessions_with_issues'] += 1
                validation_results['total_issues'] += len(session_issues)
                
                # Catégoriser les problèmes
                for issue in session_issues:
                    category = self._categorize_issue(issue)
                    validation_results['issues_by_category'][category] = \
                        validation_results['issues_by_category'].get(category, 0) + 1
            else:
                validation_results['valid_sessions'] += 1
            
            # Ajouter les résultats de validation pour cette session
            validation_results['sessions_validation'].append({
                'session_summary': session.original_summary,
                'session_date': session.planned_date,
                'issues': session_issues,
                'validation_score': self._calculate_validation_score(session_issues),
                'confidence_score': session.confidence_score
            })
        
        # Calculer les statistiques finales
        validation_results['validation_rate'] = \
            validation_results['valid_sessions'] / validation_results['total_sessions'] if validation_results['total_sessions'] > 0 else 0
        
        validation_results['average_validation_score'] = \
            sum(sv['validation_score'] for sv in validation_results['sessions_validation']) / len(validation_results['sessions_validation']) if validation_results['sessions_validation'] else 0
        
        logger.info(f"Validation terminée: {validation_results['valid_sessions']}/{validation_results['total_sessions']} sessions valides")
        return validation_results
    
    def _validate_single_session(self, session: ParsedTrainingSession) -> List[str]:
        """Valide une session individuelle et retourne la liste des problèmes"""
        issues = []
        
        # Validation du type d'entraînement
        issues.extend(self._validate_type_consistency(session))
        
        # Validation de l'intensité
        issues.extend(self._validate_intensity_consistency(session))
        
        # Validation de la structure des séries principales
        issues.extend(self._validate_main_sets_structure(session))
        
        # Validation de l'estimation de distance
        issues.extend(self._validate_distance_estimation(session))
        
        # Validation de la cohérence de durée
        issues.extend(self._validate_duration_consistency(session))
        
        return issues
    
    def _validate_type_consistency(self, session: ParsedTrainingSession) -> List[str]:
        """Valide la cohérence du type d'entraînement"""
        issues = []
        text = f"{session.original_summary} {session.original_description}".lower()
        
        if not session.type:
            issues.append("Type d'entraînement non détecté")
            return issues
        
        # Vérifier si le type détecté correspond au contenu
        if session.type == 'Intervalle' and not any(keyword in text for keyword in ['intervalle', 'fractionné', 'vma', 'vo2max']):
            if not any(char.isdigit() and 'x' in session.original_summary for char in session.original_summary):
                issues.append("Type 'Intervalle' détecté mais aucun pattern d'intervalle trouvé")
        
        elif session.type == 'Seuil' and 'seuil' not in text:
            issues.append("Type 'Seuil' détecté mais mot-clé 'seuil' absent")
        
        elif session.type == 'Allure' and not any(keyword in text for keyword in ['allure', 'tempo', 'rythme']):
            if not any(char.isdigit() and 'km' in session.original_summary for char in session.original_summary):
                issues.append("Type 'Allure' détecté mais aucune distance ou allure spécifiée")
        
        return issues
    
    def _validate_intensity_consistency(self, session: ParsedTrainingSession) -> List[str]:
        """Valide la cohérence de l'intensité"""
        issues = []
        text = f"{session.original_summary} {session.original_description}"
        
        if not session.intensity:
            issues.append("Intensité non détectée")
            return issues
        
        # Vérifier si l'intensité correspond aux allures mentionnées
        for intensity, paces in INTENSITY_PACES.items():
            if any(pace in text for pace in paces):
                if session.intensity != intensity:
                    issues.append(f"Intensité '{session.intensity}' incohérente avec l'allure détectée (attendue: {intensity})")
                break
        
        # Vérifier la cohérence avec le type d'entraînement
        if session.type == 'Intervalle' and session.intensity == 'Faible':
            issues.append("Intensité 'Faible' incohérente avec le type 'Intervalle'")
        
        elif session.type == 'Endurance' and session.intensity == 'Élevée':
            issues.append("Intensité 'Élevée' incohérente avec le type 'Endurance'")
        
        return issues
    
    def _validate_main_sets_structure(self, session: ParsedTrainingSession) -> List[str]:
        """Valide la structure des séries principales"""
        issues = []
        
        if not session.main_sets:
            issues.append("Aucune série principale détectée")
            return issues
        
        # Vérifier la cohérence avec le type d'entraînement
        if session.type == 'Intervalle':
            interval_sets = [ms for ms in session.main_sets if ms.get('type') == 'intervalle']
            if not interval_sets:
                issues.append("Type 'Intervalle' mais aucune série d'intervalle détectée")
        
        elif session.type == 'Seuil':
            seuil_sets = [ms for ms in session.main_sets if ms.get('type') == 'seuil']
            if not seuil_sets:
                issues.append("Type 'Seuil' mais aucune série de seuil détectée")
        
        # Vérifier les doublons potentiels
        durations = [ms.get('duration_minutes') for ms in session.main_sets if ms.get('duration_minutes')]
        if len(durations) != len(set(durations)):
            issues.append("Doublons potentiels détectés dans les séries principales")
        
        return issues
    
    def _validate_distance_estimation(self, session: ParsedTrainingSession) -> List[str]:
        """Valide l'estimation de distance"""
        issues = []
        
        if not session.estimated_distance_km:
            issues.append("Distance non estimée")
            return issues
        
        if not session.duration_minutes:
            issues.append("Durée manquante pour validation de la distance")
            return issues
        
        # Vérifier si la distance est raisonnable pour la durée
        expected_distance = session.duration_minutes / 6.5  # 6.5 min/km par défaut
        tolerance = expected_distance * 0.3  # 30% de tolérance
        
        if session.estimated_distance_km < expected_distance - tolerance:
            issues.append(f"Distance estimée ({session.estimated_distance_km}km) très faible pour la durée ({session.duration_minutes}min)")
        
        elif session.estimated_distance_km > expected_distance + tolerance:
            issues.append(f"Distance estimée ({session.estimated_distance_km}km) très élevée pour la durée ({session.duration_minutes}min)")
        
        return issues
    
    def _validate_duration_consistency(self, session: ParsedTrainingSession) -> List[str]:
        """Valide la cohérence de la durée"""
        issues = []
        
        if not session.duration_minutes:
            issues.append("Durée manquante")
            return issues
        
        if not session.main_sets:
            return issues
        
        # Calculer la durée totale des séries principales
        total_main_duration = 0
        for main_set in session.main_sets:
            duration = main_set.get('duration_minutes', 0)
            repetitions = main_set.get('repetitions', 1)
            total_main_duration += duration * repetitions
        
        # Vérifier si la durée totale des séries dépasse la durée de la session
        if total_main_duration > session.duration_minutes:
            issues.append(f"Durée totale des séries ({total_main_duration}min) dépasse la durée de la session ({session.duration_minutes}min)")
        
        return issues
    
    def _categorize_issue(self, issue: str) -> str:
        """Catégorise un problème de validation"""
        issue_lower = issue.lower()
        
        if 'type' in issue_lower:
            return 'type_detection'
        elif 'intensité' in issue_lower or 'allure' in issue_lower:
            return 'intensity_consistency'
        elif 'série' in issue_lower or 'intervalle' in issue_lower:
            return 'structure_validation'
        elif 'distance' in issue_lower:
            return 'distance_estimation'
        elif 'durée' in issue_lower:
            return 'duration_consistency'
        else:
            return 'other'
    
    def _calculate_validation_score(self, issues: List[str]) -> float:
        """Calcule un score de validation (0.0 = parfait, 1.0 = problèmes majeurs)"""
        if not issues:
            return 0.0
        
        # Score de base basé sur le nombre de problèmes
        base_score = min(len(issues) * 0.2, 1.0)
        
        # Pénalités pour les problèmes critiques
        critical_issues = ['durée', 'distance', 'série']
        critical_count = sum(1 for issue in issues if any(crit in issue.lower() for crit in critical_issues))
        
        critical_penalty = critical_count * 0.1
        
        return min(base_score + critical_penalty, 1.0)
    
    def generate_validation_report(self, validation_results: Dict[str, Any]) -> str:
        """Génère un rapport de validation en texte"""
        report = []
        report.append("=== RAPPORT DE VALIDATION DES SESSIONS D'ENTRAÎNEMENT ===\n")
        
        # Statistiques générales
        report.append(f"Sessions totales: {validation_results['total_sessions']}")
        report.append(f"Sessions valides: {validation_results['valid_sessions']}")
        report.append(f"Sessions avec problèmes: {validation_results['sessions_with_issues']}")
        report.append(f"Taux de validation: {validation_results['validation_rate']:.1%}")
        report.append(f"Score moyen: {validation_results['average_validation_score']:.2f}\n")
        
        # Problèmes par catégorie
        if validation_results['issues_by_category']:
            report.append("PROBLÈMES PAR CATÉGORIE:")
            for category, count in validation_results['issues_by_category'].items():
                report.append(f"  {category}: {count}")
            report.append("")
        
        # Détail des sessions avec problèmes
        sessions_with_issues = [sv for sv in validation_results['sessions_validation'] if sv['issues']]
        if sessions_with_issues:
            report.append("SESSIONS AVEC PROBLÈMES:")
            for session_validation in sessions_with_issues[:10]:  # Limiter à 10 pour la lisibilité
                report.append(f"  {session_validation['session_summary']} ({session_validation['session_date']})")
                for issue in session_validation['issues']:
                    report.append(f"    - {issue}")
                report.append("")
        
        return "\n".join(report) 