#!/usr/bin/env python3
"""
Script pour enrichir les WorkoutPlan existants avec les données parsées
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any
import json

# Ajouter le répertoire backend au path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy.orm import Session
from sqlmodel import select
from app.core.database import get_session
from app.domain.entities.workout_plan import WorkoutPlan
from app.domain.services.training_enrichment_service import TrainingEnrichmentService


def enrich_existing_workout_plans():
    """Enrichit tous les WorkoutPlan existants avec les données parsées"""
    
    print("🚀 Démarrage de l'enrichissement des WorkoutPlan existants")
    print("=" * 60)
    
    # Initialiser le service
    enrichment_service = TrainingEnrichmentService()
    
    # Récupérer tous les WorkoutPlan
    session = next(get_session())
    
    try:
        # Récupérer tous les WorkoutPlan
        stmt = select(WorkoutPlan)
        workout_plans = session.exec(stmt).all()
        
        print(f"📋 {len(workout_plans)} WorkoutPlan trouvés")
        
        if not workout_plans:
            print("❌ Aucun WorkoutPlan à enrichir")
            return
        
        # Grouper par utilisateur
        users_plans = {}
        for plan in workout_plans:
            user_id = plan.user_id
            if user_id not in users_plans:
                users_plans[user_id] = []
            users_plans[user_id].append(plan)
        
        print(f"👥 {len(users_plans)} utilisateurs avec des plans")
        
        total_enriched = 0
        
        # Traiter chaque utilisateur
        for user_id, plans in users_plans.items():
            print(f"\n👤 Utilisateur {user_id}: {len(plans)} plans")
            
            # Convertir les plans en événements pour le pipeline
            events = []
            for plan in plans:
                event = {
                    "summary": plan.name,
                    "description": plan.description or "",
                    "planned_date": plan.planned_date.isoformat() + "T00:00:00Z",
                    "duration_minutes": plan.planned_duration or 60,
                    "is_completed": plan.is_completed,
                    "source": "workout_plan"
                }
                events.append(event)
            
            # Enrichir avec le service
            try:
                report = enrichment_service.enrich_workout_plans_from_events(
                    events, user_id, session
                )
                
                enriched_count = report["enrichment_summary"]["workout_plans_enriched"]
                total_enriched += enriched_count
                
                print(f"  ✅ {enriched_count}/{len(plans)} plans enrichis")
                
                # Afficher les détails du parsing
                parsing_results = report["parsing_results"]
                print(f"  📊 Score de confiance moyen: {parsing_results['confidence_scores']['average']}")
                print(f"  🏃 Types détectés: {parsing_results['types_detected']}")
                
            except Exception as e:
                print(f"  ❌ Erreur pour l'utilisateur {user_id}: {e}")
                continue
        
        print(f"\n🎉 Enrichissement terminé!")
        print(f"📊 Total enrichi: {total_enriched}/{len(workout_plans)} plans")
        
        # Afficher quelques exemples
        print(f"\n📋 Exemples de plans enrichis:")
        enriched_plans = session.exec(
            select(WorkoutPlan).where(WorkoutPlan.parsed_type.is_not(None))
        ).limit(5).all()
        
        for plan in enriched_plans:
            print(f"  • {plan.name}")
            print(f"    Type: {plan.parsed_type} (confiance: {plan.parsed_confidence_score})")
            print(f"    Intensité: {plan.parsed_intensity}")
            if plan.parsed_estimated_distance:
                print(f"    Distance: {plan.parsed_estimated_distance}km")
            print()
        
    except Exception as e:
        print(f"❌ Erreur générale: {e}")
        raise
    finally:
        session.close()


def main():
    """Fonction principale"""
    try:
        enrich_existing_workout_plans()
        print("\n✅ Script terminé avec succès!")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main()) 