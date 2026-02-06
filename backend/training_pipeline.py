#!/usr/bin/env python3
"""
Pipeline unifié de traitement des sessions d'entraînement.
Fusionne parsing, corrections automatiques, validation et import en base.
"""

import json
import os
import re
import logging
import argparse
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from zoneinfo import ZoneInfo

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/training_pipeline.log'),
        logging.StreamHandler()
    ]
)

@dataclass
class TrainingSession:
    """Structure de données pour une session d'entraînement"""
    original_summary: str
    original_description: str
    planned_date: str
    duration_minutes: int
    is_completed: bool
    source: str
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

class TrainingPipeline:
    """Pipeline unifié de traitement des sessions d'entraînement"""
    
    def __init__(self, input_file: str = "data/imported_calendar_20250725_185303.json"):
        self.input_file = Path(input_file)
        self.sessions_dir = Path("data/parsed_sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)
        
        self.stats = {
            'total_sessions': 0,
            'parsed_sessions': 0,
            'corrected_sessions': 0,
            'validation_issues': 0,
            'errors': 0
        }
    
    def run_full_pipeline(self) -> Dict[str, Any]:
        """Exécute le pipeline complet de A à Z"""
        logging.info("🚀 Démarrage du pipeline unifié de traitement des sessions")
        
        try:
            # ÉTAPE 1: Parsing initial
            logging.info("📋 ÉTAPE 1: Parsing des événements Google Calendar")
            sessions = self.parse_events()
            
            # ÉTAPE 2: Corrections automatiques
            logging.info("🔧 ÉTAPE 2: Corrections automatiques")
            self.apply_corrections(sessions)
            
            # ÉTAPE 3: Validation et rapports
            logging.info("✅ ÉTAPE 3: Validation et génération de rapports")
            validation_results = self.validate_sessions(sessions)
            
            # ÉTAPE 4: Sauvegarde des sessions
            logging.info("💾 ÉTAPE 4: Sauvegarde des sessions")
            self.save_sessions(sessions)
            
            # ÉTAPE 5: Génération du rapport final
            logging.info("📊 ÉTAPE 5: Génération du rapport final")
            final_report = self.generate_final_report(sessions, validation_results)
            
            logging.info("🎉 Pipeline terminé avec succès !")
            return final_report
            
        except Exception as e:
            logging.error(f"❌ Erreur dans le pipeline: {e}")
            self.stats['errors'] += 1
            raise
    
    def parse_events(self) -> List[TrainingSession]:
        """Parse les événements Google Calendar"""
        if not self.input_file.exists():
            raise FileNotFoundError(f"Fichier d'entrée non trouvé: {self.input_file}")
        
        with open(self.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get('imported_events', [])
        self.stats['total_sessions'] = len(events)
        
        sessions = []
        for event in events:
            try:
                session = self.parse_event(event)
                if session:
                    sessions.append(session)
                    self.stats['parsed_sessions'] += 1
            except Exception as e:
                logging.error(f"Erreur lors du parsing de l'événement: {e}")
                self.stats['errors'] += 1
        
        logging.info(f"✅ {len(sessions)} sessions parsées sur {self.stats['total_sessions']} événements")
        return sessions
    
    def parse_event(self, event: Dict) -> Optional[TrainingSession]:
        """Parse un événement individuel"""
        summary = event.get('summary', '')
        description = event.get('description', '')
        planned_date = event.get('planned_date', '')
        duration_minutes = event.get('duration_minutes', 0)
        is_completed = event.get('is_completed', False)
        source = event.get('source', 'google_calendar')
        
        # Créer la session de base
        session = TrainingSession(
            original_summary=summary,
            original_description=description,
            planned_date=planned_date,
            duration_minutes=duration_minutes,
            is_completed=is_completed,
            source=source
        )
        
        # Extraire les informations structurées
        session.type = self._extract_training_type(summary, description)
        session.intensity = self._extract_intensity(summary, description)
        
        # Extraire la structure (warmup, main_sets, cooldown)
        structure = self._extract_structure(summary, description, duration_minutes)
        session.warmup = structure.get('warmup')
        session.main_sets = structure.get('main_sets')
        session.cooldown = structure.get('cooldown')
        
        # Estimer les métadonnées
        session.estimated_distance_km = self._estimate_distance(summary, description, duration_minutes)
        session.estimated_pace_min_km = self._extract_pace(description)
        session.estimated_heart_rate = self._extract_heart_rate(description)
        
        # Calculer le score de confiance
        session.confidence_score = self._calculate_confidence_score(session)
        paris = ZoneInfo("Europe/Paris")
        session.processed_at = datetime.now(tz=paris).isoformat()
        
        return session
    
    def _extract_training_type(self, summary: str, description: str) -> str:
        """Extrait le type d'entraînement"""
        summary_lower = summary.lower()
        description_lower = description.lower()
        
        # Vérifier d'abord les cas spéciaux dans le summary
        if 'rando/course' in summary_lower:
            return 'Rando-Course'
        
        # Types principaux
        if 'endurance' in summary_lower:
            return 'Endurance'
        elif 'seuil' in summary_lower:
            return 'Seuil'
        elif 'allure' in summary_lower:
            return 'Allure'
        elif 'pyramide' in summary_lower:
            return 'Pyramide'
        elif 'salle' in summary_lower or 'musculation' in summary_lower:
            return 'Musculation'
        elif 'rando' in summary_lower:
            if 'alternant' in description_lower or 'marche' in description_lower:
                return 'Rando-Course'
            return 'Randonnée'
        elif 'veille' in summary_lower or 'lignes droites' in summary_lower:
            return 'Veille de course'
        
        return 'Autre'
    
    def _extract_intensity(self, summary: str, description: str) -> str:
        """Extrait l'intensité de l'entraînement"""
        description_lower = description.lower()
        
        # Priorité aux allures spécifiques
        if '4:19' in description or '4:30' in description:
            return 'Élevée'
        elif '5:03' in description or '5:17' in description:
            return 'Modérée'
        elif '6:40' in description or '7:00' in description:
            return 'Faible'
        
        # Fallback sur le type
        summary_lower = summary.lower()
        if 'seuil' in summary_lower or 'allure' in summary_lower:
            return 'Modérée'
        elif 'endurance' in summary_lower:
            return 'Faible'
        elif 'pyramide' in summary_lower:
            return 'Modérée'
        
        return 'Modérée'
    
    def _extract_structure(self, summary: str, description: str, duration_minutes: int) -> Dict:
        """Extrait la structure de l'entraînement"""
        warmup = None
        main_sets = []
        cooldown = None
        
        # 1. Extraire les intervalles avec position
        interval_pattern = r'(\d+)x(\d+(?:min|km|m|sec)) en ([^+]+)'
        for m in re.finditer(interval_pattern, description):
            reps, duration_raw, pace = m.group(1), m.group(2), m.group(3)
            duration_raw = duration_raw.lower()
            
            if 'sec' in duration_raw:
                key = 'duration'
                value = duration_raw
            elif 'min' in duration_raw:
                key = 'duration'
                value = duration_raw
            elif 'km' in duration_raw or 'm' in duration_raw:
                key = 'distance'
                value = duration_raw
            else:
                key, value = 'unknown', duration_raw
            
            # Nettoyer le pace en retirant la récupération
            clean_pace = pace.strip()
            if 'avec' in clean_pace and 'récupération' in clean_pace:
                clean_pace = clean_pace.split('avec')[0].strip()
            
            # Extraire la récupération de manière contextuelle
            context_start = max(0, m.start() - 50)
            context_end = min(len(description), m.end() + 100)
            context = description[context_start:context_end]
            
            # Chercher la récupération spécifique pour cet intervalle
            recovery = self._extract_recovery_time(context, reps)
            
            main_sets.append({
                'reps': int(reps),
                key: value,
                'pace': clean_pace,
                'recovery': recovery,
                'type': (self._extract_training_type(summary, description) or 'Autre').lower(),
                '_pos': m.start()
            })
        
        # 2. Extraire les blocs simples (avec déduplication)
        seen = set()
        for s in main_sets:
            key = (s.get('reps'), s.get('duration'), s.get('distance'), s.get('pace'))
            seen.add(key)
        
        # Créer un set des positions déjà couvertes par les intervalles
        interval_positions = set()
        for s in main_sets:
            if s.get('_pos') is not None:
                interval_positions.add(s.get('_pos'))
        
        for m in re.finditer(r'(\d+(?:km|min|m|sec)) en ([^+]+)', description):
            duration_raw = m.group(1).lower()
            pace = m.group(2).strip()
            start = m.start(1)
            
            # Skip si précédé par \dx (évite les doublons avec les intervalles)
            if start >= 3:
                left = description[max(0, start-6):start].lower()
                if re.search(r'\d+\s*x\s*$', left):
                    continue
            
            # Skip si déjà capturé par un intervalle
            key = (1, duration_raw if 'min' in duration_raw else None,
                   duration_raw if 'km' in duration_raw or 'm' in duration_raw else None, pace)
            if key in seen:
                continue
            
            # Skip si dans une zone déjà couverte par un intervalle
            if any(abs(start - pos) < 20 for pos in interval_positions):
                continue
            
            # Vérification supplémentaire : si on trouve un pattern d'intervalle dans la zone
            context_start = max(0, start - 10)
            context_end = min(len(description), start + 20)
            context = description[context_start:context_end]
            if re.search(r'\d+x\d+', context):
                continue
            
            if 'km' in duration_raw or 'm' in duration_raw:
                key_name = 'distance'
                value = duration_raw
            else:
                key_name = 'duration'
                value = duration_raw
            
            main_sets.append({
                'reps': 1,
                key_name: value,
                'pace': pace,
                'recovery': None,
                'type': (self._extract_training_type(summary, description) or 'Autre').lower(),
                '_pos': m.start()
            })
        
        # 3. Extraire les pyramides (seulement si mot-clé pyramide explicite et pas déjà extrait)
        summary_lower = summary.lower()
        if 'pyramide' in summary_lower and not main_sets:
            for pm in re.finditer(r'(\d+min)', summary):
                main_sets.append({
                    'reps': 1,
                    'duration': pm.group(1),
                    'type': 'pyramide',
                    'pace': "5:03/km",
                    'recovery': "2min",
                    '_pos': len(description) + pm.start()  # après le texte principal
                })
        
        # 4. Trier par position puis nettoyer le champ technique
        main_sets.sort(key=lambda s: s.get('_pos', 1_000_000))
        for s in main_sets:
            s.pop('_pos', None)
        
        # 5. Extraire warmup et cooldown
        # Warm-up au début : "Courir 20min" ou "Courir 1h"
        wu = re.search(r'\bcourir\s+((\d+)h)?\s*(\d+)?\s*min', description, re.I)
        if wu:
            h = int(wu.group(2) or 0)
            m = int(wu.group(3) or 0)
            warmup = f"{h*60+m}min" if h else f"{m}min"
        
        # Cooldown : dernier "+ Xmin ..." (pas d'allure figée)
        cd = list(re.finditer(r'\+\s*(\d+)\s*min\b', description, re.I))
        if cd:
            cooldown = f"{cd[-1].group(1)}min"
        
        # 6. Fallback pour les séances continues
        is_continuous_session = ('endurance' in summary.lower() or 'rando' in summary.lower())
        if is_continuous_session and not main_sets:
            pace_match = re.search(r'(\d+:\d+)[^/]*/(\d+:\d+)', description)
            if pace_match:
                pace_range = f"{pace_match.group(1)}-{pace_match.group(2)}/km"
            else:
                pace_range = "6:40-7:00/km"
            
            main_sets = [{
                'reps': 1,
                'duration': f"{duration_minutes}min",
                'type': 'endurance',
                'pace': pace_range,
                'recovery': None
            }]
        
        # 7. Fallback pour la musculation
        if not main_sets and 'salle' in summary.lower():
            main_sets = [{
                'reps': None,
                'duration': f"{duration_minutes}min",
                'type': 'libre',
                'pace': None,
                'recovery': None
            }]
        
        # Stocker les main_sets pour l'estimation de distance
        self._last_main_sets = main_sets
        self._last_warmup = warmup
        self._last_cooldown = cooldown
        
        return {
            'warmup': warmup,
            'main_sets': main_sets,
            'cooldown': cooldown
        }
    
    def _extract_recovery_time(self, description: str, reps: str) -> Optional[str]:
        """Extrait le temps de récupération"""
        t = description.lower()
        
        # 1) minutes+secondes: 1min30, 2min30, etc.
        m = re.search(r'(\d+)\s*min(?:ute)?s?\s*(\d{1,2})\s*(?:sec(?:onde)?s?)?', t)
        if m:
            return f"{int(m.group(1))}min{int(m.group(2)):02d}"
        
        # 1bis) forme sans espace: 1min30, 2min30, etc.
        m = re.search(r'(\d+)min(\d{1,2})', t)
        if m:
            return f"{int(m.group(1))}min{int(m.group(2)):02d}"
        
        # 2) forme à l'athlé: 1'30", 2'45", etc.
        m = re.search(r'(\d+)\s*[\'′]\s*(\d{1,2})\s*(?:["″s])?', t)
        if m:
            return f"{int(m.group(1))}min{int(m.group(2)):02d}"
        
        # 3) Pattern pour "entre chaque Xmin" (priorité haute)
        between_pattern = r'entre chaque (\d+)min'
        between_match = re.search(between_pattern, t)
        if between_match:
            return f"{between_match.group(1)}min"
        
        # 4) Pattern pour "avec Xmin de récupération entre chaque"
        with_between_pattern = r'avec (\d+)min de récupération entre chaque'
        with_between_match = re.search(with_between_pattern, t)
        if with_between_match:
            return f"{with_between_match.group(1)}min"
        
        # 5) Pattern pour "entre chaque Xsec"
        between_sec_pattern = r'entre chaque (\d+)sec'
        between_sec_match = re.search(between_sec_pattern, t)
        if between_sec_match:
            return f"{between_sec_match.group(1)}sec"
        
        # 6) Pattern pour les secondes
        recovery_sec_pattern = r'(\d+)\s*(?:s|sec|secs|secondes?)'
        recovery_sec_match = re.search(recovery_sec_pattern, t)
        if recovery_sec_match and 'récup' in t:
            return f"{int(recovery_sec_match.group(1))}sec"
        
        # 7) Pattern pour les minutes
        recovery_pattern = r'(\d+)\s*min(?:ute)?s?'
        recovery_match = re.search(recovery_pattern, t)
        if recovery_match and 'récup' in t:
            return f"{int(recovery_match.group(1))}min"
        
        return "2min"
    
    def _mmss_to_speed(self, minsec: str) -> float:
        """Convertit une allure mm:ss en vitesse min/km"""
        m, s = map(int, re.split(r'[:\'′]', minsec))
        return m + s/60.0
    
    def _estimate_distance(self, summary: str, description: str, duration_minutes: int) -> Optional[float]:
        """Estime la distance en km"""
        if not duration_minutes:
            return None
        
        # Si main_sets présents, calculer à partir des blocs
        try:
            sets = getattr(self, "_last_main_sets", None)
        except:
            sets = None
        
        if sets:
            total_km = 0.0
            fallback_pace = 6.7  # min/km endurance douce
            
            for s in sets:
                pace = None
                if s.get('pace'):
                    m = re.search(r'(\d+[:\'′]\d{2})', s['pace'])
                    if m:
                        pace = self._mmss_to_speed(m.group(1))
                
                if 'distance' in s and s['distance']:
                    km = float(re.sub(r'km$', '', s['distance']))
                    total_km += km
                elif 'duration' in s and s['duration']:
                    duration_str = s['duration']
                    if 'sec' in duration_str:
                        secs = float(re.sub(r'sec$', '', duration_str))
                        mins = secs / 60.0
                    else:
                        mins = float(re.sub(r'min$', '', duration_str))
                    total_km += mins / (pace or fallback_pace)
            
            # Ajouter warmup/cooldown si connus
            if hasattr(self, '_last_warmup') and self._last_warmup:
                warmup_mins = float(re.sub(r'min$', '', self._last_warmup))
                total_km += warmup_mins / fallback_pace
            
            if hasattr(self, '_last_cooldown') and self._last_cooldown:
                cooldown_mins = float(re.sub(r'min$', '', self._last_cooldown))
                total_km += cooldown_mins / fallback_pace
            
            return round(total_km, 1)
        
        # Sinon, retomber sur les heuristiques existantes
        summary_lower = summary.lower()
        description_lower = description.lower()
        
        # Randonnée mixte
        if ('rando' in summary_lower and 
            ('alternant' in description_lower or 'marche' in description_lower)):
            return round(duration_minutes / 8.0, 1)
        
        # Endurance
        if 'endurance' in summary_lower:
            if '6:05' in description or '6:15' in description:
                return round(duration_minutes / 6.1, 1)
            elif '6:40' in description or '7:00' in description:
                return round(duration_minutes / 6.8, 1)
            else:
                return round(duration_minutes / 6.5, 1)
        
        # Seuil/Allure
        if 'seuil' in summary_lower or 'allure' in summary_lower:
            if '2x' in summary or '3x' in summary or '4x' in summary:
                return round(duration_minutes / 7.0, 1)
            else:
                return round(duration_minutes / 6.5, 1)
        
        return round(duration_minutes / 6.5, 1)
    
    def _extract_pace(self, description: str) -> Optional[str]:
        """Extrait l'allure cible"""
        d = description
        
        # Plage d'allure: mm:ss - mm:ss ou mm'ss" - mm'ss"
        m = re.search(r'(\d+[:\'′]\d{2}).*?[/ ]km.*?(\d+[:\'′]\d{2})', d, re.I)
        if m:
            a = m.group(1).replace('′', "'").replace(":", "'")
            b = m.group(2).replace('′', "'").replace(":", "'")
            a_clean = a.replace("'", ":")
            b_clean = b.replace("'", ":")
            return f"{a_clean}-{b_clean}/km"
        
        # Allure simple: mm:ss/km ou mm'ss"/km
        m = re.search(r'(\d+[:\'′]\d{2})\s*(?:["″s])?\s*/?\s*km', d, re.I)
        if m:
            a = m.group(1).replace('′', "'").replace(":", "'")
            a_clean = a.replace("'", ":")
            return f"{a_clean}/km"
        
        return None
    
    def _extract_heart_rate(self, description: str) -> Optional[str]:
        """Extrait la fréquence cardiaque cible (prend la plus haute)"""
        matches = re.findall(r'(\d+)(?:-(\d+))?\s*bpm', description, flags=re.I)
        if not matches:
            return None
        
        # Normaliser en (low, high)
        ranges = []
        for low, high in matches:
            lo = int(low)
            hi = int(high) if high else lo
            ranges.append((lo, hi))
        
        # Retourner la plage avec le high le plus élevé
        lo, hi = max(ranges, key=lambda t: t[1])
        return f"{lo}-{hi}bpm" if lo != hi else f"{hi}bpm"
    
    def _calculate_confidence_score(self, session: TrainingSession) -> float:
        """Calcule un score de confiance"""
        score = 0.5  # Score de base
        
        if session.main_sets:
            score += 0.2
        if session.estimated_distance_km:
            score += 0.1
        if session.estimated_pace_min_km:
            score += 0.1
        if session.estimated_heart_rate:
            score += 0.1
        
        return min(score, 1.0)
    
    def apply_corrections(self, sessions: List[TrainingSession]):
        """Applique les corrections automatiques"""
        corrected_count = 0
        
        for session in sessions:
            corrections = []
            corrected = False
            
            # Correction des intensités incohérentes
            if self._has_inconsistent_intensity(session):
                if self._fix_intensity_consistency(session):
                    corrections.append("Intensité corrigée")
                    corrected = True
            
            # Correction des distances estimées
            if self._has_inconsistent_distance(session):
                if self._fix_distance_estimation(session):
                    corrections.append("Distance estimée corrigée")
                    corrected = True
            
            # Correction des main_sets manquants
            if self._has_missing_main_sets(session):
                if self._fix_missing_main_sets(session):
                    corrections.append("Main_sets ajoutés")
                    corrected = True
            
            if corrected:
                corrected_count += 1
                session.corrections = corrections
                paris = ZoneInfo("Europe/Paris")
                session.processed_at = datetime.now(tz=paris).isoformat()
                session.confidence_score = self._calculate_confidence_score(session)
        
        self.stats['corrected_sessions'] = corrected_count
        logging.info(f"✅ {corrected_count} sessions corrigées")
    
    def _has_inconsistent_intensity(self, session: TrainingSession) -> bool:
        """Détecte les intensités incohérentes"""
        summary_lower = session.original_summary.lower()
        description_lower = session.original_description.lower()
        
        if 'seuil' in summary_lower and session.intensity == 'Faible':
            return True
        if 'allure' in summary_lower and session.intensity == 'Faible':
            return True
        if 'endurance' in summary_lower and session.intensity == 'Élevée':
            return True
        
        if '4:19' in description_lower or '4:30' in description_lower:
            if session.intensity != 'Élevée':
                return True
        
        if '5:03' in description_lower or '5:17' in description_lower:
            if session.intensity not in ['Modérée', 'Élevée']:
                return True
        
        if '6:40' in description_lower or '7:00' in description_lower:
            if session.intensity != 'Faible':
                return True
        
        return False
    
    def _fix_intensity_consistency(self, session: TrainingSession) -> bool:
        """Corrige les intensités incohérentes"""
        summary_lower = session.original_summary.lower()
        description_lower = session.original_description.lower()
        
        if '4:19' in description_lower or '4:30' in description_lower:
            session.intensity = 'Élevée'
            return True
        elif '5:03' in description_lower or '5:17' in description_lower:
            session.intensity = 'Modérée'
            return True
        elif '6:40' in description_lower or '7:00' in description_lower:
            session.intensity = 'Faible'
            return True
        elif 'seuil' in summary_lower or 'allure' in summary_lower:
            session.intensity = 'Modérée'
            return True
        elif 'endurance' in summary_lower:
            session.intensity = 'Faible'
            return True
        
        return False
    
    def _has_inconsistent_distance(self, session: TrainingSession) -> bool:
        """Détecte les distances estimées incohérentes"""
        if not session.estimated_distance_km or not session.duration_minutes:
            return False
        
        expected_distance = self._estimate_distance(
            session.original_summary, 
            session.original_description, 
            session.duration_minutes
        )
        
        if not expected_distance:
            return False
        
        tolerance = expected_distance * 0.25
        return abs(session.estimated_distance_km - expected_distance) > tolerance
    
    def _fix_distance_estimation(self, session: TrainingSession) -> bool:
        """Corrige l'estimation de distance"""
        if not session.duration_minutes:
            return False
        
        expected_distance = self._estimate_distance(
            session.original_summary, 
            session.original_description, 
            session.duration_minutes
        )
        
        if expected_distance:
            session.estimated_distance_km = expected_distance
            return True
        
        return False
    
    def _has_missing_main_sets(self, session: TrainingSession) -> bool:
        """Détecte les main_sets manquants"""
        summary_lower = session.original_summary.lower()
        return ('seuil' in summary_lower or 'allure' in summary_lower or 'pyramide' in summary_lower) and not session.main_sets
    
    def _fix_missing_main_sets(self, session: TrainingSession) -> bool:
        """Corrige les main_sets manquants"""
        summary_lower = session.original_summary.lower()
        
        if 'seuil' in summary_lower:
            block_pattern = r'(\d+)x(\d+)(?:min|km)'
            blocks = re.findall(block_pattern, session.original_summary)
            
            if blocks:
                session.main_sets = []
                for reps, duration in blocks:
                    session.main_sets.append({
                        'reps': int(reps),
                        'duration': f"{duration}min",
                        'type': 'seuil',
                        'pace': "5:03/km",
                        'recovery': "2min"
                    })
                return True
        
        return False
    
    def validate_sessions(self, sessions: List[TrainingSession]) -> Dict[str, Any]:
        """Valide toutes les sessions"""
        validation_results = {
            'total_sessions': len(sessions),
            'sessions_with_issues': 0,
            'total_issues': 0,
            'issue_types': {},
            'detailed_results': []
        }
        
        for session in sessions:
            issues = []
            
            # Validation des types
            type_issues = self._validate_type_consistency(session)
            issues.extend(type_issues)
            
            # Validation des intensités
            intensity_issues = self._validate_intensity_consistency(session)
            issues.extend(intensity_issues)
            
            # Validation de la structure
            structure_issues = self._validate_main_sets_structure(session)
            issues.extend(structure_issues)
            
            # Validation des distances
            distance_issues = self._validate_distance_estimation(session)
            issues.extend(distance_issues)
            
            # Validation de la cohérence des durées
            duration_issues = self._validate_duration_consistency(session)
            issues.extend(duration_issues)
            
            if issues:
                validation_results['sessions_with_issues'] += 1
                validation_results['total_issues'] += len(issues)
                
                for issue in issues:
                    issue_type = self._categorize_issue(issue)
                    validation_results['issue_types'][issue_type] = validation_results['issue_types'].get(issue_type, 0) + 1
            
            validation_results['detailed_results'].append({
                'summary': session.original_summary,
                'issues': issues,
                'validation_score': self._calculate_validation_score(issues)
            })
        
        self.stats['validation_issues'] = validation_results['total_issues']
        return validation_results
    
    def _validate_type_consistency(self, session: TrainingSession) -> List[str]:
        """Valide la cohérence du type"""
        issues = []
        summary_lower = session.original_summary.lower()
        description_lower = session.original_description.lower()
        
        if 'endurance' in summary_lower and session.type != 'Endurance':
            issues.append(f"Type incohérent: 'endurance' dans summary mais type='{session.type}'")
        
        if 'seuil' in summary_lower and session.type != 'Seuil':
            issues.append(f"Type incohérent: 'seuil' dans summary mais type='{session.type}'")
        
        if 'rando' in summary_lower and session.type not in ['Randonnée', 'Rando-Course']:
            issues.append(f"Type incohérent: 'rando' dans summary mais type='{session.type}'")
        
        return issues
    
    def _validate_intensity_consistency(self, session: TrainingSession) -> List[str]:
        """Valide la cohérence de l'intensité"""
        issues = []
        summary_lower = session.original_summary.lower()
        description_lower = session.original_description.lower()
        
        if 'seuil' in summary_lower and session.intensity == 'Faible':
            issues.append(f"Intensité incohérente: seuil avec intensité 'Faible'")
        
        if '4:19' in description_lower or '4:30' in description_lower:
            if session.intensity != 'Élevée':
                issues.append(f"Intensité incohérente: allure 4:19-4:30/km mais intensité '{session.intensity}'")
        
        return issues
    
    def _validate_main_sets_structure(self, session: TrainingSession) -> List[str]:
        """Valide la structure des main_sets"""
        issues = []
        summary_lower = session.original_summary.lower()
        
        if ('seuil' in summary_lower or 'allure' in summary_lower or 'pyramide' in summary_lower) and not session.main_sets:
            issues.append("Main_sets manquant pour une séance structurée")
        
        return issues
    
    def _validate_distance_estimation(self, session: TrainingSession) -> List[str]:
        """Valide l'estimation de distance"""
        issues = []
        summary_lower = session.original_summary.lower()
        
        if ('endurance' in summary_lower or 'rando' in summary_lower) and session.estimated_distance_km is None:
            issues.append("Distance estimée manquante pour une séance continue")
        
        return issues
    
    def _validate_duration_consistency(self, session: TrainingSession) -> List[str]:
        """Valide la cohérence entre durée planifiée et somme des blocs"""
        issues = []
        
        if not session.main_sets or not session.duration_minutes:
            return issues
        
        # Calculer la durée totale des blocs
        total_block_duration = 0
        
        # Ajouter warmup
        if session.warmup:
            warmup_mins = float(re.sub(r'min$', '', session.warmup))
            total_block_duration += warmup_mins
        
        # Ajouter main_sets
        for block in session.main_sets:
            if 'duration' in block and block['duration']:
                if 'sec' in block['duration']:
                    secs = float(re.sub(r'sec$', '', block['duration']))
                    total_block_duration += secs / 60.0
                else:
                    mins = float(re.sub(r'min$', '', block['duration']))
                    reps = block.get('reps', 1)
                    if reps is not None:
                        total_block_duration += mins * reps
                    else:
                        total_block_duration += mins
        
        # Ajouter cooldown
        if session.cooldown:
            cooldown_mins = float(re.sub(r'min$', '', session.cooldown))
            total_block_duration += cooldown_mins
        
        # Vérifier l'écart
        if total_block_duration > 0:
            planned_duration = session.duration_minutes
            diff_percent = abs(total_block_duration - planned_duration) / planned_duration * 100
            
            if diff_percent > 10:
                issues.append(f"Écart important entre durée planifiée ({planned_duration}min) et somme des blocs ({total_block_duration:.1f}min): {diff_percent:.1f}%")
        
        return issues
    
    def _categorize_issue(self, issue: str) -> str:
        """Catégorise un problème"""
        issue_lower = issue.lower()
        
        if 'type' in issue_lower:
            return 'Type'
        elif 'intensité' in issue_lower:
            return 'Intensité'
        elif 'main_sets' in issue_lower:
            return 'Structure'
        elif 'distance' in issue_lower:
            return 'Distance'
        else:
            return 'Autre'
    
    def _calculate_validation_score(self, issues: List[str]) -> float:
        """Calcule un score de validation"""
        base_score = 1.0
        
        penalties = {
            'type': 0.2,
            'intensity': 0.15,
            'structure': 0.25,
            'distance': 0.1
        }
        
        for issue in issues:
            if 'type' in issue.lower():
                base_score -= penalties['type']
            elif 'intensité' in issue.lower():
                base_score -= penalties['intensity']
            elif 'main_sets' in issue.lower():
                base_score -= penalties['structure']
            elif 'distance' in issue.lower():
                base_score -= penalties['distance']
        
        return max(0.0, base_score)
    
    def save_sessions(self, sessions: List[TrainingSession]):
        """Sauvegarde les sessions dans des fichiers JSON"""
        for session in sessions:
            # Extraire la date pour créer le nom de fichier
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', session.planned_date)
            if date_match:
                date_str = date_match.group(1)
                year, month = date_str.split('-')[:2]
                
                # Créer le dossier de l'année/mois
                session_dir = self.sessions_dir / year / month
                session_dir.mkdir(parents=True, exist_ok=True)
                
                # Créer le nom de fichier (nettoyer les caractères spéciaux et tronquer)
                safe_summary = re.sub(r'[^\w\s-]', '', session.original_summary)
                safe_summary = safe_summary.replace(' ', '_').replace('/', '_')
                
                # Tronquer à ~80 caractères et ajouter un hash court
                if len(safe_summary) > 80:
                    summary_hash = hashlib.md5(safe_summary.encode()).hexdigest()[:8]
                    safe_summary = safe_summary[:80] + f"_{summary_hash}"
                
                filename = f"{date_str}_{safe_summary}.json"
                filepath = session_dir / filename
                
                # Sauvegarder la session
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(asdict(session), f, indent=2, ensure_ascii=False)
    
    def generate_final_report(self, sessions: List[TrainingSession], validation_results: Dict) -> Dict[str, Any]:
        """Génère le rapport final"""
        avg_validation_score = sum(r['validation_score'] for r in validation_results['detailed_results']) / len(sessions) if sessions else 0
        success_rate = ((validation_results['total_sessions'] - validation_results['sessions_with_issues']) / validation_results['total_sessions'] * 100) if validation_results['total_sessions'] > 0 else 0
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'pipeline_stats': self.stats,
            'validation_summary': {
                'total_sessions': validation_results['total_sessions'],
                'sessions_with_issues': validation_results['sessions_with_issues'],
                'total_issues': validation_results['total_issues'],
                'avg_validation_score': round(avg_validation_score, 3),
                'success_rate': round(success_rate, 1)
            },
            'issue_types': validation_results['issue_types'],
            'detailed_results': validation_results['detailed_results']
        }
        
        # Sauvegarder le rapport
        report_file = self.logs_dir / 'pipeline_report.json'
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # Générer un rapport texte
        self._generate_text_report(report)
        
        return report
    
    def _generate_text_report(self, report: Dict):
        """Génère un rapport texte lisible"""
        report_file = self.logs_dir / 'pipeline_report.txt'
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("RAPPORT FINAL DU PIPELINE DE TRAITEMENT\n")
            f.write("=" * 50 + "\n\n")
            
            # Statistiques du pipeline
            pipeline_stats = report['pipeline_stats']
            f.write(f"📊 STATISTIQUES DU PIPELINE\n")
            f.write(f"  • Sessions totales: {pipeline_stats['total_sessions']}\n")
            f.write(f"  • Sessions parsées: {pipeline_stats['parsed_sessions']}\n")
            f.write(f"  • Sessions corrigées: {pipeline_stats['corrected_sessions']}\n")
            f.write(f"  • Problèmes de validation: {pipeline_stats['validation_issues']}\n")
            f.write(f"  • Erreurs: {pipeline_stats['errors']}\n\n")
            
            # Résumé de validation
            validation = report['validation_summary']
            f.write(f"✅ RÉSUMÉ DE VALIDATION\n")
            f.write(f"  • Sessions totales: {validation['total_sessions']}\n")
            f.write(f"  • Sessions avec problèmes: {validation['sessions_with_issues']}\n")
            f.write(f"  • Problèmes totaux: {validation['total_issues']}\n")
            f.write(f"  • Score de validation moyen: {validation['avg_validation_score']}\n")
            f.write(f"  • Taux de succès: {validation['success_rate']}%\n\n")
            
            # Types de problèmes
            f.write(f"🔍 TYPES DE PROBLÈMES\n")
            for issue_type, count in report['issue_types'].items():
                f.write(f"  • {issue_type}: {count} problèmes\n")
            f.write("\n")
            
            # Sessions avec problèmes
            f.write(f"⚠️ SESSIONS AVEC PROBLÈMES\n")
            for result in report['detailed_results']:
                if result['issues']:
                    f.write(f"\n📅 {result['summary']}\n")
                    f.write(f"   Score: {result['validation_score']:.2f}\n")
                    for issue in result['issues']:
                        f.write(f"   • {issue}\n")
            
            f.write(f"\n✅ SESSIONS VALIDÉES\n")
            for result in report['detailed_results']:
                if not result['issues']:
                    f.write(f"  • {result['summary']} (Score: {result['validation_score']:.2f})\n")


def main():
    """Fonction principale"""
    parser = argparse.ArgumentParser(description="Pipeline unifié de traitement des sessions d'entraînement")
    parser.add_argument("--input", 
                       default=os.getenv("TRAINING_INPUT", "data/imported_calendar_20250725_185303.json"),
                       help="Fichier d'entrée JSON (défaut: variable d'environnement TRAINING_INPUT ou fichier par défaut)")
    args = parser.parse_args()
    
    print("🚀 Pipeline unifié de traitement des sessions d'entraînement")
    print("=" * 70)
    print(f"📁 Fichier d'entrée: {args.input}")
    
    pipeline = TrainingPipeline(input_file=args.input)
    
    try:
        report = pipeline.run_full_pipeline()
        
        print("\n📊 RÉSULTATS FINAUX:")
        print(f"  • Sessions traitées: {report['pipeline_stats']['total_sessions']}")
        print(f"  • Sessions parsées: {report['pipeline_stats']['parsed_sessions']}")
        print(f"  • Sessions corrigées: {report['pipeline_stats']['corrected_sessions']}")
        print(f"  • Taux de succès: {report['validation_summary']['success_rate']}%")
        print(f"  • Score de validation moyen: {report['validation_summary']['avg_validation_score']}")
        
        print(f"\n📁 Rapports générés:")
        print(f"  • JSON: logs/pipeline_report.json")
        print(f"  • Texte: logs/pipeline_report.txt")
        print(f"  • Logs: logs/training_pipeline.log")
        
        print("\n🎉 Pipeline terminé avec succès !")
        
    except Exception as e:
        print(f"\n❌ Erreur dans le pipeline: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main()) 