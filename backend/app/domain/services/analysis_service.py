"""
Service d'Analyse - Domain Layer
Gère les comparaisons prévision vs réel et génère des insights
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from ..entities.workout_plan import WorkoutPlan
from ..entities.activity import Activity


class AnalysisService:
    """
    Service pour analyser les performances et comparer prévision vs réel
    Implémente les comparaisons définies dans l'audit §4.2
    """
    

    

    
    def generate_training_insights(
        self, 
        user_activities: List[Activity],
        user_plans: List[WorkoutPlan],
        weeks: int = 4
    ) -> Dict[str, Any]:
        """
        Génère des insights d'entraînement basés sur l'historique
        
        Args:
            user_activities: Activités de l'utilisateur
            user_plans: Plans d'entraînement de l'utilisateur
            weeks: Nombre de semaines à analyser
            
        Returns:
            Insights et recommandations d'entraînement
        """
        cutoff_date = datetime.utcnow() - timedelta(weeks=weeks)
        
        # Filtrer les données récentes
        recent_activities = [
            act for act in user_activities 
            if act.start_date >= cutoff_date
        ]
        recent_plans = [
            plan for plan in user_plans 
            if plan.planned_date >= cutoff_date.date()
        ]
        
        # Calculs d'insights
        total_distance = sum(act.distance for act in recent_activities) / 1000  # km
        total_time = sum(act.moving_time for act in recent_activities) / 3600  # heures
        avg_pace = self._calculate_avg_pace(recent_activities)
        
        # Analyse de consistance
        planned_vs_actual = len([p for p in recent_plans if p.is_completed])
        plan_adherence = (planned_vs_actual / len(recent_plans)) * 100 if recent_plans else 0
        
        return {
            'period_weeks': weeks,
            'total_distance_km': round(total_distance, 1),
            'total_time_hours': round(total_time, 1),
            'avg_pace_min_km': round(avg_pace, 2) if avg_pace else None,
            'activities_count': len(recent_activities),
            'plans_count': len(recent_plans),
            'plan_adherence_pct': round(plan_adherence, 1),
            'avg_distance_per_week': round(total_distance / weeks, 1),
            'recommendations': self._generate_training_recommendations(
                recent_activities, recent_plans, plan_adherence
            )
        }
    
    def _calculate_variance(self, planned: float, actual: float) -> float:
        """Calcule l'écart en pourcentage entre prévu et réel"""
        if planned == 0:
            return 0.0
        return ((actual - planned) / planned) * 100
    
    def _calculate_pace(self, distance_m: float, time_s: int) -> float:
        """Calcule le pace en min/km"""
        if distance_m == 0:
            return 0.0
        distance_km = distance_m / 1000
        time_min = time_s / 60
        return time_min / distance_km
    

    
    def _calculate_avg_pace(self, activities: List[Activity]) -> Optional[float]:
        """Calcule le pace moyen d'une liste d'activités"""
        if not activities:
            return None
        
        total_time = sum(act.moving_time for act in activities)
        total_distance = sum(act.distance for act in activities) / 1000  # km
        
        if total_distance == 0:
            return None
        
        return (total_time / 60) / total_distance  # min/km
    
    def _generate_training_recommendations(
        self,
        activities: List[Activity],
        plans: List[WorkoutPlan],
        adherence: float
    ) -> List[str]:
        """Génère des recommandations d'entraînement"""
        recommendations = []
        
        if adherence < 50:
            recommendations.append("📅 Planifiez des créneaux d'entraînement plus réalistes")
        elif adherence > 90:
            recommendations.append("🏆 Excellente régularité! Pensez à progresser")
        
        if len(activities) < 2:
            recommendations.append("🔄 Augmentez la fréquence d'entraînement")
        elif len(activities) > 10:
            recommendations.append("⚡ Attention au surentraînement - prévoyez des repos")
        
        return recommendations 