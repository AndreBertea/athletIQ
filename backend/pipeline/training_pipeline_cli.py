#!/usr/bin/env python3
"""
Script CLI pour exécuter le pipeline de traitement des entraînements
Utile pour réanalyser d'anciens imports ou faire du débogage
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Any

# Ajouter le répertoire parent au path pour les imports
sys.path.append(str(Path(__file__).parent.parent))

from app.domain.services.training_parser import TrainingParser, ParsedTrainingSession
from app.domain.services.training_corrections import TrainingCorrections
from app.domain.services.training_validation import TrainingValidation

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TrainingPipelineCLI:
    """Interface CLI pour le pipeline de traitement des entraînements"""
    
    def __init__(self):
        self.parser = TrainingParser()
        self.corrections = TrainingCorrections()
        self.validation = TrainingValidation()
    
    def run_pipeline(self, input_file: str, output_file: str = None, 
                    save_individual_sessions: bool = False) -> Dict[str, Any]:
        """Exécute le pipeline complet sur un fichier d'entrée"""
        logger.info(f"🚀 Démarrage du pipeline CLI sur {input_file}")
        
        try:
            # ÉTAPE 1: Charger les données d'entrée
            events = self._load_input_file(input_file)
            logger.info(f"📋 {len(events)} événements chargés depuis {input_file}")
            
            # ÉTAPE 2: Parsing des événements
            parsed_sessions = []
            for event in events:
                parsed_session = self.parser.parse_event(event)
                if parsed_session:
                    parsed_sessions.append(parsed_session)
            
            logger.info(f"✅ Parsing terminé: {len(parsed_sessions)} sessions parsées")
            
            # ÉTAPE 3: Corrections automatiques
            corrected_sessions = self.corrections.apply_corrections(parsed_sessions)
            logger.info(f"🔧 Corrections appliquées: {len(self.corrections.corrections_applied)}")
            
            # ÉTAPE 4: Validation
            validation_results = self.validation.validate_sessions(corrected_sessions)
            logger.info(f"✅ Validation terminée: {validation_results['valid_sessions']}/{validation_results['total_sessions']} sessions valides")
            
            # ÉTAPE 5: Sauvegarde des résultats
            final_report = self._generate_final_report(
                events, parsed_sessions, corrected_sessions, validation_results
            )
            
            if output_file:
                self._save_output_file(final_report, output_file)
                logger.info(f"💾 Rapport sauvegardé dans {output_file}")
            
            if save_individual_sessions:
                self._save_individual_sessions(corrected_sessions)
                logger.info("💾 Sessions individuelles sauvegardées")
            
            # ÉTAPE 6: Affichage du rapport
            self._display_report(final_report)
            
            logger.info("🎉 Pipeline CLI terminé avec succès !")
            return final_report
            
        except Exception as e:
            logger.error(f"❌ Erreur dans le pipeline CLI: {e}")
            raise
    
    def _load_input_file(self, input_file: str) -> List[Dict]:
        """Charge les données depuis un fichier JSON"""
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extraire les événements selon le format du fichier
            if 'imported_events' in data:
                return data['imported_events']
            elif isinstance(data, list):
                return data
            else:
                raise ValueError("Format de fichier non reconnu")
                
        except Exception as e:
            logger.error(f"Erreur lors du chargement du fichier {input_file}: {e}")
            raise
    
    def _generate_final_report(self, events: List[Dict], 
                             parsed_sessions: List[ParsedTrainingSession],
                             corrected_sessions: List[ParsedTrainingSession],
                             validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Génère le rapport final du pipeline"""
        corrections_summary = self.corrections.get_corrections_summary()
        
        report = {
            'pipeline_execution': {
                'input_file': 'input_file',
                'total_events_processed': len(events),
                'sessions_parsed': len(parsed_sessions),
                'sessions_corrected': len(corrected_sessions),
                'execution_timestamp': self._get_timestamp()
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
            'sessions_details': [
                {
                    'summary': session.original_summary,
                    'date': session.planned_date,
                    'type': session.type,
                    'intensity': session.intensity,
                    'confidence_score': session.confidence_score,
                    'corrections': session.corrections,
                    'main_sets': session.main_sets
                }
                for session in corrected_sessions
            ]
        }
        
        return report
    
    def _save_output_file(self, report: Dict[str, Any], output_file: str):
        """Sauvegarde le rapport dans un fichier JSON"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde du rapport: {e}")
            raise
    
    def _save_individual_sessions(self, sessions: List[ParsedTrainingSession]):
        """Sauvegarde chaque session dans un fichier séparé"""
        sessions_dir = Path("data/parsed_sessions_cli")
        sessions_dir.mkdir(parents=True, exist_ok=True)
        
        for session in sessions:
            try:
                # Créer le nom du fichier basé sur la date et le résumé
                date_str = session.planned_date.replace('-', '')
                summary_clean = "".join(c for c in session.original_summary if c.isalnum() or c in (' ', '-', '_')).rstrip()
                filename = f"{date_str}__{summary_clean}.json"
                
                filepath = sessions_dir / filename
                
                # Convertir la session en dictionnaire
                session_dict = {
                    'original_summary': session.original_summary,
                    'original_description': session.original_description,
                    'planned_date': session.planned_date,
                    'duration_minutes': session.duration_minutes,
                    'is_completed': session.is_completed,
                    'source': session.source,
                    'type': session.type,
                    'intensity': session.intensity,
                    'warmup': session.warmup,
                    'main_sets': session.main_sets,
                    'cooldown': session.cooldown,
                    'estimated_distance_km': session.estimated_distance_km,
                    'estimated_pace_min_km': session.estimated_pace_min_km,
                    'estimated_heart_rate': session.estimated_heart_rate,
                    'confidence_score': session.confidence_score,
                    'processed_at': session.processed_at,
                    'corrections': session.corrections
                }
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)
                    
            except Exception as e:
                logger.error(f"Erreur lors de la sauvegarde de la session {session.original_summary}: {e}")
                continue
    
    def _display_report(self, report: Dict[str, Any]):
        """Affiche un résumé du rapport dans la console"""
        print("\n" + "="*60)
        print("RAPPORT DU PIPELINE DE TRAITEMENT DES ENTRAÎNEMENTS")
        print("="*60)
        
        # Statistiques générales
        exec_info = report['pipeline_execution']
        print(f"\n📊 STATISTIQUES GÉNÉRALES:")
        print(f"   Événements traités: {exec_info['total_events_processed']}")
        print(f"   Sessions parsées: {exec_info['sessions_parsed']}")
        print(f"   Sessions corrigées: {exec_info['sessions_corrected']}")
        
        # Résultats du parsing
        parsing_results = report['parsing_results']
        confidence = parsing_results['confidence_scores']
        print(f"\n🎯 RÉSULTATS DU PARSING:")
        print(f"   Score de confiance moyen: {confidence['average']:.2f}")
        print(f"   Score min: {confidence['min']:.2f}")
        print(f"   Score max: {confidence['max']:.2f}")
        
        # Types détectés
        types = parsing_results['types_detected']
        if types:
            print(f"\n🏃 TYPES D'ENTRAÎNEMENT DÉTECTÉS:")
            for type_name, count in types.items():
                print(f"   {type_name}: {count}")
        
        # Corrections appliquées
        corrections = report['corrections_applied']
        if corrections['total_corrections'] > 0:
            print(f"\n🔧 CORRECTIONS APPLIQUÉES:")
            print(f"   Total: {corrections['total_corrections']}")
            for correction_type, count in corrections['corrections_by_type'].items():
                print(f"   {correction_type}: {count}")
        
        # Résultats de validation
        validation = report['validation_results']
        print(f"\n✅ RÉSULTATS DE VALIDATION:")
        print(f"   Sessions valides: {validation['valid_sessions']}/{validation['total_sessions']}")
        print(f"   Taux de validation: {validation['validation_rate']:.1%}")
        print(f"   Score moyen: {validation['average_validation_score']:.2f}")
        
        if validation['issues_by_category']:
            print(f"\n⚠️  PROBLÈMES PAR CATÉGORIE:")
            for category, count in validation['issues_by_category'].items():
                print(f"   {category}: {count}")
        
        print("\n" + "="*60)
    
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
    
    def _get_timestamp(self) -> str:
        """Retourne un timestamp ISO"""
        from datetime import datetime
        return datetime.now().isoformat()


def main():
    """Point d'entrée principal du script CLI"""
    parser = argparse.ArgumentParser(
        description="Pipeline CLI pour le traitement des entraînements",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python training_pipeline_cli.py data/imported_calendar_20250728_021749.json
  python training_pipeline_cli.py input.json -o output.json
  python training_pipeline_cli.py input.json --save-sessions
        """
    )
    
    parser.add_argument(
        'input_file',
        help='Fichier JSON d\'entrée contenant les événements à traiter'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Fichier JSON de sortie pour le rapport (optionnel)'
    )
    
    parser.add_argument(
        '--save-sessions',
        action='store_true',
        help='Sauvegarder chaque session dans un fichier séparé'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Afficher les logs détaillés'
    )
    
    args = parser.parse_args()
    
    # Configuration du niveau de log
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Vérifier que le fichier d'entrée existe
    if not Path(args.input_file).exists():
        print(f"❌ Erreur: Le fichier {args.input_file} n'existe pas")
        sys.exit(1)
    
    try:
        # Exécuter le pipeline
        pipeline = TrainingPipelineCLI()
        pipeline.run_pipeline(
            input_file=args.input_file,
            output_file=args.output,
            save_individual_sessions=args.save_sessions
        )
        
    except Exception as e:
        print(f"❌ Erreur lors de l'exécution du pipeline: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 