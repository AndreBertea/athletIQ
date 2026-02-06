#!/usr/bin/env python3
"""
Script de nettoyage des fichiers obsolètes du pipeline d'entraînement
Supprime les fichiers identifiés comme inutiles dans l'audit
"""
import os
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PipelineCleanup:
    """Service de nettoyage des fichiers obsolètes du pipeline"""
    
    def __init__(self, data_dir: str = "data", logs_dir: str = "logs"):
        self.data_dir = Path(data_dir)
        self.logs_dir = Path(logs_dir)
        self.backup_dir = Path("data/backup_cleanup")
        
    def cleanup_obsolete_files(self, dry_run: bool = True) -> Dict[str, Any]:
        """Nettoie tous les fichiers obsolètes identifiés dans l'audit"""
        logger.info(f"🧹 Démarrage du nettoyage des fichiers obsolètes (dry_run: {dry_run})")
        
        cleanup_report = {
            'dry_run': dry_run,
            'timestamp': datetime.now().isoformat(),
            'files_removed': [],
            'files_kept': [],
            'errors': [],
            'summary': {}
        }
        
        try:
            # 1. Nettoyer les snapshots JSON multiples
            self._cleanup_snapshot_files(cleanup_report, dry_run)
            
            # 2. Nettoyer les fichiers de séances individuelles
            self._cleanup_individual_session_files(cleanup_report, dry_run)
            
            # 3. Nettoyer les logs redondants
            self._cleanup_redundant_logs(cleanup_report, dry_run)
            
            # 4. Nettoyer les fichiers de rapport dupliqués
            self._cleanup_duplicate_reports(cleanup_report, dry_run)
            
            # Générer le résumé
            cleanup_report['summary'] = {
                'total_files_removed': len(cleanup_report['files_removed']),
                'total_files_kept': len(cleanup_report['files_kept']),
                'total_errors': len(cleanup_report['errors']),
                'space_saved_mb': self._calculate_space_saved(cleanup_report['files_removed'])
            }
            
            logger.info(f"✅ Nettoyage terminé: {cleanup_report['summary']['total_files_removed']} fichiers supprimés")
            return cleanup_report
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du nettoyage: {e}")
            cleanup_report['errors'].append(str(e))
            return cleanup_report
    
    def _cleanup_snapshot_files(self, report: Dict, dry_run: bool):
        """Nettoie les snapshots JSON multiples d'import Google Calendar"""
        logger.info("📋 Nettoyage des snapshots JSON d'import...")
        
        # Chercher tous les fichiers imported_calendar_*.json
        snapshot_pattern = "imported_calendar_*.json"
        snapshot_files = list(self.data_dir.glob(snapshot_pattern))
        
        if not snapshot_files:
            logger.info("Aucun fichier snapshot trouvé")
            return
        
        # Trier par date de modification (plus récent en premier)
        snapshot_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        
        # Garder seulement le plus récent
        files_to_keep = snapshot_files[:1]
        files_to_remove = snapshot_files[1:]
        
        logger.info(f"Fichiers snapshot trouvés: {len(snapshot_files)}")
        logger.info(f"Fichiers à conserver: {len(files_to_keep)}")
        logger.info(f"Fichiers à supprimer: {len(files_to_remove)}")
        
        for file_path in files_to_keep:
            report['files_kept'].append({
                'path': str(file_path),
                'reason': 'Plus récent snapshot d\'import',
                'size_mb': file_path.stat().st_size / (1024 * 1024)
            })
        
        for file_path in files_to_remove:
            try:
                if not dry_run:
                    # Créer une sauvegarde avant suppression
                    backup_path = self.backup_dir / file_path.name
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, backup_path)
                    
                    # Supprimer le fichier
                    file_path.unlink()
                
                report['files_removed'].append({
                    'path': str(file_path),
                    'reason': 'Snapshot obsolète',
                    'size_mb': file_path.stat().st_size / (1024 * 1024),
                    'backup_created': not dry_run
                })
                
            except Exception as e:
                error_msg = f"Erreur lors de la suppression de {file_path}: {e}"
                logger.error(error_msg)
                report['errors'].append(error_msg)
    
    def _cleanup_individual_session_files(self, report: Dict, dry_run: bool):
        """Nettoie les fichiers de séances individuelles"""
        logger.info("📁 Nettoyage des fichiers de séances individuelles...")
        
        sessions_dir = self.data_dir / "parsed_sessions"
        if not sessions_dir.exists():
            logger.info("Répertoire parsed_sessions non trouvé")
            return
        
        # Chercher tous les fichiers JSON dans les sous-répertoires
        session_files = list(sessions_dir.rglob("*.json"))
        
        if not session_files:
            logger.info("Aucun fichier de séance trouvé")
            return
        
        logger.info(f"Fichiers de séances trouvés: {len(session_files)}")
        
        # Analyser les fichiers pour détecter les doublons
        file_groups = self._group_session_files(session_files)
        
        for group_key, files in file_groups.items():
            if len(files) > 1:
                # Garder le plus récent, supprimer les autres
                files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                files_to_keep = files[:1]
                files_to_remove = files[1:]
                
                for file_path in files_to_keep:
                    report['files_kept'].append({
                        'path': str(file_path),
                        'reason': f'Plus récent fichier pour {group_key}',
                        'size_mb': file_path.stat().st_size / (1024 * 1024)
                    })
                
                for file_path in files_to_remove:
                    try:
                        if not dry_run:
                            # Créer une sauvegarde avant suppression
                            backup_path = self.backup_dir / file_path.relative_to(self.data_dir)
                            backup_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(file_path, backup_path)
                            
                            # Supprimer le fichier
                            file_path.unlink()
                        
                        report['files_removed'].append({
                            'path': str(file_path),
                            'reason': f'Doublon de {group_key}',
                            'size_mb': file_path.stat().st_size / (1024 * 1024),
                            'backup_created': not dry_run
                        })
                        
                    except Exception as e:
                        error_msg = f"Erreur lors de la suppression de {file_path}: {e}"
                        logger.error(error_msg)
                        report['errors'].append(error_msg)
            else:
                # Fichier unique, le conserver
                file_path = files[0]
                report['files_kept'].append({
                    'path': str(file_path),
                    'reason': 'Fichier unique',
                    'size_mb': file_path.stat().st_size / (1024 * 1024)
                })
    
    def _group_session_files(self, files: List[Path]) -> Dict[str, List[Path]]:
        """Groupe les fichiers de séances par contenu similaire"""
        groups = {}
        
        for file_path in files:
            try:
                # Extraire la date et le résumé du nom de fichier
                # Format attendu: YYYYMMDD__Summary.json
                filename = file_path.stem
                if '__' in filename:
                    date_part = filename.split('__')[0]
                    summary_part = '__'.join(filename.split('__')[1:])
                    group_key = f"{date_part}_{summary_part}"
                else:
                    group_key = filename
                
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(file_path)
                
            except Exception as e:
                logger.warning(f"Impossible de traiter le fichier {file_path}: {e}")
                # Créer un groupe unique pour ce fichier
                groups[str(file_path)] = [file_path]
        
        return groups
    
    def _cleanup_redundant_logs(self, report: Dict, dry_run: bool):
        """Nettoie les logs redondants"""
        logger.info("📝 Nettoyage des logs redondants...")
        
        if not self.logs_dir.exists():
            logger.info("Répertoire logs non trouvé")
            return
        
        # Chercher les fichiers de log du pipeline
        log_files = list(self.logs_dir.glob("*training_pipeline*.log"))
        
        if not log_files:
            logger.info("Aucun fichier de log du pipeline trouvé")
            return
        
        # Garder seulement les logs des 7 derniers jours
        cutoff_date = datetime.now() - timedelta(days=7)
        
        for log_file in log_files:
            try:
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                
                if file_mtime < cutoff_date:
                    if not dry_run:
                        # Créer une sauvegarde avant suppression
                        backup_path = self.backup_dir / "logs" / log_file.name
                        backup_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(log_file, backup_path)
                        
                        # Supprimer le fichier
                        log_file.unlink()
                    
                    report['files_removed'].append({
                        'path': str(log_file),
                        'reason': f'Log ancien ({file_mtime.strftime("%Y-%m-%d")})',
                        'size_mb': log_file.stat().st_size / (1024 * 1024),
                        'backup_created': not dry_run
                    })
                else:
                    report['files_kept'].append({
                        'path': str(log_file),
                        'reason': f'Log récent ({file_mtime.strftime("%Y-%m-%d")})',
                        'size_mb': log_file.stat().st_size / (1024 * 1024)
                    })
                    
            except Exception as e:
                error_msg = f"Erreur lors du traitement du log {log_file}: {e}"
                logger.error(error_msg)
                report['errors'].append(error_msg)
    
    def _cleanup_duplicate_reports(self, report: Dict, dry_run: bool):
        """Nettoie les rapports dupliqués"""
        logger.info("📊 Nettoyage des rapports dupliqués...")
        
        # Chercher les fichiers de rapport
        report_patterns = ["pipeline_report*.json", "*_report.json"]
        
        for pattern in report_patterns:
            report_files = list(self.data_dir.glob(pattern))
            
            if not report_files:
                continue
            
            # Trier par date de modification
            report_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # Garder seulement les 3 plus récents
            files_to_keep = report_files[:3]
            files_to_remove = report_files[3:]
            
            for file_path in files_to_keep:
                report['files_kept'].append({
                    'path': str(file_path),
                    'reason': 'Rapport récent conservé',
                    'size_mb': file_path.stat().st_size / (1024 * 1024)
                })
            
            for file_path in files_to_remove:
                try:
                    if not dry_run:
                        # Créer une sauvegarde avant suppression
                        backup_path = self.backup_dir / file_path.name
                        backup_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, backup_path)
                        
                        # Supprimer le fichier
                        file_path.unlink()
                    
                    report['files_removed'].append({
                        'path': str(file_path),
                        'reason': 'Rapport ancien',
                        'size_mb': file_path.stat().st_size / (1024 * 1024),
                        'backup_created': not dry_run
                    })
                    
                except Exception as e:
                    error_msg = f"Erreur lors de la suppression du rapport {file_path}: {e}"
                    logger.error(error_msg)
                    report['errors'].append(error_msg)
    
    def _calculate_space_saved(self, removed_files: List[Dict]) -> float:
        """Calcule l'espace disque économisé en MB"""
        total_size = sum(file_info.get('size_mb', 0) for file_info in removed_files)
        return round(total_size, 2)
    
    def generate_cleanup_report(self, report: Dict) -> str:
        """Génère un rapport de nettoyage en texte"""
        output = []
        output.append("=" * 60)
        output.append("RAPPORT DE NETTOYAGE DES FICHIERS OBSOLÈTES")
        output.append("=" * 60)
        
        summary = report['summary']
        output.append(f"\n📊 RÉSUMÉ:")
        output.append(f"   Mode dry-run: {'Oui' if report['dry_run'] else 'Non'}")
        output.append(f"   Fichiers supprimés: {summary['total_files_removed']}")
        output.append(f"   Fichiers conservés: {summary['total_files_kept']}")
        output.append(f"   Erreurs: {summary['total_errors']}")
        output.append(f"   Espace économisé: {summary['space_saved_mb']} MB")
        
        if report['files_removed']:
            output.append(f"\n🗑️  FICHIERS SUPPRIMÉS:")
            for file_info in report['files_removed']:
                output.append(f"   {file_info['path']}")
                output.append(f"     Raison: {file_info['reason']}")
                output.append(f"     Taille: {file_info['size_mb']} MB")
                if file_info.get('backup_created'):
                    output.append(f"     Sauvegarde créée: Oui")
                output.append("")
        
        if report['errors']:
            output.append(f"\n❌ ERREURS:")
            for error in report['errors']:
                output.append(f"   {error}")
        
        output.append("\n" + "=" * 60)
        return "\n".join(output)


def main():
    """Point d'entrée principal du script de nettoyage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Nettoyage des fichiers obsolètes du pipeline d'entraînement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples d'utilisation:
  python cleanup_obsolete_files.py --dry-run
  python cleanup_obsolete_files.py --execute
  python cleanup_obsolete_files.py --execute --backup
        """
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Exécuter réellement le nettoyage (par défaut: mode dry-run)'
    )
    
    parser.add_argument(
        '--data-dir',
        default='data',
        help='Répertoire des données (défaut: data)'
    )
    
    parser.add_argument(
        '--logs-dir',
        default='logs',
        help='Répertoire des logs (défaut: logs)'
    )
    
    parser.add_argument(
        '--output-report',
        help='Fichier de sortie pour le rapport JSON'
    )
    
    args = parser.parse_args()
    
    # Exécuter le nettoyage
    cleanup = PipelineCleanup(args.data_dir, args.logs_dir)
    report = cleanup.cleanup_obsolete_files(dry_run=not args.execute)
    
    # Afficher le rapport
    print(cleanup.generate_cleanup_report(report))
    
    # Sauvegarder le rapport JSON si demandé
    if args.output_report:
        try:
            with open(args.output_report, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"\n📄 Rapport JSON sauvegardé dans: {args.output_report}")
        except Exception as e:
            print(f"❌ Erreur lors de la sauvegarde du rapport: {e}")


if __name__ == "__main__":
    main() 