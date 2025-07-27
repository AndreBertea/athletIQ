# Archive - Code Legacy AthlétIQ

Ce dossier contient l'ancien code d'AthlétIQ avant la migration vers l'architecture moderne React + FastAPI.

## 📁 Structure

### `legacy-python/`
Scripts Python originaux remplacés par le backend FastAPI :
- `app.py` - Ancienne application Dash
- `auth_server.py` - Serveur Flask pour OAuth
- `fetch_strava_runs.py` - Script de récupération Strava
- `train_models.py` - Entraînement modèles ML
- `plotly_*.py` - Scripts de visualisation
- `report_*.py` - Génération de rapports

### `legacy-frontend/`
Anciens fichiers frontend remplacés par React :
- `*.html` - Pages HTML statiques
- `js/` - JavaScript vanilla
- `src/` - Ancien code source

### `legacy-config/`
Anciens fichiers de configuration :
- `strava_config.json` - Config avec secrets exposés (⚠️ non sécurisé)
- `environement.yml` - Conda environment (typo dans le nom)
- `requirements.txt` - Anciennes dépendances

### `external-libs/`
Bibliothèques externes archivées :
- `AutoViz/` - Bibliothèque de visualisation automatique
- `AutoViz_Plots/` - Graphiques générés

## 🔄 Migration

L'ancien code a été migré vers la nouvelle architecture en **Sprint 1** :

| Ancien | Nouveau | Améliorations |
|--------|---------|---------------|
| Scripts Python éparpillés | Backend FastAPI structuré | Architecture DDD, API REST |
| HTML/JS statique | React + TypeScript | Composants réutilisables, state management |
| Secrets en dur | Variables d'environnement | Sécurité renforcée |
| Pas de tests | Tests complets | Qualité et fiabilité |
| Déploiement manuel | CI/CD automatisé | DevOps moderne |

## 📊 Fonctionnalités Conservées

Toutes les fonctionnalités de l'ancien code ont été portées :
- ✅ Récupération activités Strava
- ✅ Visualisations graphiques
- ✅ Calculs de métriques
- ✅ Segmentation d'activités
- ✅ Analyse des données

## 🚫 Utilisation

**⚠️ Important :** Ce code est archivé et ne doit **PAS** être utilisé en production :
- Secrets exposés dans `strava_config.json`
- Pas de validation des entrées
- Pas de gestion d'erreurs robuste
- Pas de tests automatisés
- Code dupliqué et non maintenu

## 📚 Référence

Consultez le [rapport de migration](../audit/sprint1_migration.md) pour :
- Détails complets de la migration
- Mapping ancien → nouveau code
- Justifications des choix techniques
- Architecture de la nouvelle version

---

*Code archivé le : Décembre 2024*  
*Version actuelle : AthlétIQ v2.0 (React + FastAPI)* 