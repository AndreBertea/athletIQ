"""
Service d'Import CSV - Domain Layer
Gère l'import de plans d'entraînement depuis un fichier CSV
"""
import csv
import io
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import UUID

from ..entities.workout_plan import WorkoutPlan, WorkoutType, IntensityZone, WorkoutPlanCreate
from sqlmodel import Session


class CSVImportService:
    """
    Service pour importer des plans d'entraînement depuis un fichier CSV
    """
    
    # Mapping des types d'entraînement CSV vers notre enum
    WORKOUT_TYPE_MAPPING = {
        'trail': WorkoutType.LONG_RUN,
        'vma': WorkoutType.INTERVAL,
        'seuil': WorkoutType.TEMPO,
        'ef': WorkoutType.EASY_RUN,
        'récupération': WorkoutType.RECOVERY,
        'fartlek': WorkoutType.FARTLEK,
        'côtes': WorkoutType.HILL_REPEAT,
        'course': WorkoutType.RACE,
        'spécifique': WorkoutType.HILL_REPEAT,
        'strides': WorkoutType.INTERVAL,
        'shake-out': WorkoutType.EASY_RUN,
    }
    
    # Mapping des zones d'intensité
    INTENSITY_ZONE_MAPPING = {
        'zone 1': IntensityZone.ZONE_1,
        'zone 2': IntensityZone.ZONE_2,
        'zone 3': IntensityZone.ZONE_3,
        'zone 4': IntensityZone.ZONE_4,
        'zone 5': IntensityZone.ZONE_5,
    }
    
    def parse_csv_content(self, csv_content: str, user_id: UUID) -> List[WorkoutPlanCreate]:
        """
        Parse le contenu CSV et retourne une liste de WorkoutPlanCreate
        
        Args:
            csv_content: Contenu du fichier CSV
            user_id: ID de l'utilisateur
            
        Returns:
            Liste de WorkoutPlanCreate
        """
        plans = []
        
        # Lire le CSV
        csv_file = io.StringIO(csv_content)
        reader = csv.DictReader(csv_file, delimiter='\t')  # Séparateur tabulation
        
        for row in reader:
            try:
                plan = self._parse_row(row, user_id)
                if plan:
                    plans.append(plan)
            except Exception as e:
                print(f"Erreur lors du parsing de la ligne: {row}, erreur: {e}")
                continue
        
        return plans
    
    def _parse_row(self, row: Dict[str, str], user_id: UUID) -> Optional[WorkoutPlanCreate]:
        """
        Parse une ligne du CSV
        
        Args:
            row: Dictionnaire représentant une ligne du CSV
            user_id: ID de l'utilisateur
            
        Returns:
            WorkoutPlanCreate ou None si erreur
        """
        # Vérifier les champs obligatoires
        if not row.get('Date') or not row.get('Type') or not row.get('Km'):
            return None
        
        # Parser la date
        try:
            date_obj = datetime.strptime(row['Date'], '%d/%m/%Y').date()
        except ValueError:
            print(f"Date invalide: {row['Date']}")
            return None
        
        # Parser la distance
        try:
            distance = float(row['Km'].replace(',', '.'))
        except ValueError:
            print(f"Distance invalide: {row['Km']}")
            return None
        
        # Mapper le type d'entraînement
        workout_type = self._map_workout_type(row['Type'].lower())
        if not workout_type:
            print(f"Type d'entraînement non reconnu: {row['Type']}")
            return None
        
        # Parser les champs optionnels
        elevation_gain = self._parse_optional_float(row.get('D+ (m)'))
        pace = self._parse_optional_float(row.get('allure'))
        duration = self._parse_optional_int(row.get('durée'))
        rpe = self._parse_optional_int(row.get('rpe'))
        week = self._parse_optional_int(row.get('Semaine'))
        
        # Mapper la zone d'intensité
        intensity_zone = None
        if row.get('zone d\'intensité'):
            intensity_zone = self._map_intensity_zone(row['zone d\'intensité'].lower())
        
        # Créer le nom du plan
        name = f"{row['Type']} - {distance}km"
        if elevation_gain:
            name += f" ({elevation_gain}m D+)"
        
        return WorkoutPlanCreate(
            name=name,
            workout_type=workout_type,
            planned_date=date_obj,
            planned_distance=distance,
            planned_duration=duration,
            planned_pace=pace,
            planned_elevation_gain=elevation_gain,
            intensity_zone=intensity_zone,
            description=row.get('description', ''),
            coach_notes=row.get('notes du coach', ''),
            phase=row.get('phase', ''),
            week=week,
            rpe=rpe
        )
    
    def _map_workout_type(self, csv_type: str) -> Optional[WorkoutType]:
        """Mappe le type CSV vers notre enum WorkoutType"""
        return self.WORKOUT_TYPE_MAPPING.get(csv_type)
    
    def _map_intensity_zone(self, csv_zone: str) -> Optional[IntensityZone]:
        """Mappe la zone CSV vers notre enum IntensityZone"""
        return self.INTENSITY_ZONE_MAPPING.get(csv_zone)
    
    def _parse_optional_float(self, value: Optional[str]) -> Optional[float]:
        """Parse une valeur optionnelle en float"""
        if not value or value.strip() == '':
            return None
        try:
            return float(value.replace(',', '.'))
        except ValueError:
            return None
    
    def _parse_optional_int(self, value: Optional[str]) -> Optional[int]:
        """Parse une valeur optionnelle en int"""
        if not value or value.strip() == '':
            return None
        try:
            return int(float(value.replace(',', '.')))
        except ValueError:
            return None
    
    def import_plans_to_database(self, session: Session, plans: List[WorkoutPlanCreate], user_id: UUID) -> Dict[str, Any]:
        """
        Importe les plans dans la base de données
        
        Args:
            session: Session de base de données
            plans: Liste des plans à importer
            user_id: ID de l'utilisateur
            
        Returns:
            Résultat de l'import avec statistiques
        """
        imported_count = 0
        errors = []
        
        for plan_data in plans:
            try:
                # Créer l'entité WorkoutPlan
                plan = WorkoutPlan(
                    **plan_data.dict(),
                    user_id=user_id
                )
                
                session.add(plan)
                imported_count += 1
                
            except Exception as e:
                errors.append(f"Erreur lors de l'import du plan {plan_data.name}: {str(e)}")
        
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            return {
                "success": False,
                "message": f"Erreur lors de la sauvegarde: {str(e)}",
                "imported_count": 0,
                "total_count": len(plans),
                "errors": errors
            }
        
        return {
            "success": True,
            "message": f"Import réussi: {imported_count} plans importés",
            "imported_count": imported_count,
            "total_count": len(plans),
            "errors": errors
        }


# Instance globale du service
csv_import_service = CSVImportService() 