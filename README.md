# AthletIQ - Plateforme d'Analyse d'Entraînement Sportif

AthletIQ est une application web complète pour l'analyse et le suivi des entraînements sportifs, intégrant Strava et Google Calendar pour une gestion optimale des plans d'entraînement.

## 🚀 Fonctionnalités

- **Synchronisation Strava** : Import automatique des activités sportives
- **Intégration Google Calendar** : Gestion des plans d'entraînement
- **Analyse détaillée** : Visualisations et statistiques avancées
- **Interface moderne** : React + TypeScript avec Tailwind CSS
- **API REST** : Backend FastAPI avec authentification JWT

## 📋 Prérequis

- Python 3.8+
- Node.js 16+
- Compte Strava développeur
- Compte Google Cloud Platform

## 🛠️ Installation

### 1. Cloner le repository

```bash
git clone https://github.com/votre-username/athletIQ.git
cd athletIQ
```

### 2. Configuration Backend

```bash
cd backend

# Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos vraies valeurs
```

### 3. Configuration Frontend

```bash
cd frontend

# Installer les dépendances
npm install

# Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos vraies valeurs
```

### 4. Configuration des Services

#### Strava OAuth
1. Créer une application sur [Strava API](https://www.strava.com/settings/api)
2. Récupérer `STRAVA_CLIENT_ID` et `STRAVA_CLIENT_SECRET`
3. Configurer l'URL de callback : `http://localhost:8000/api/v1/auth/strava/callback`

#### Google Calendar OAuth
1. Créer un projet sur [Google Cloud Console](https://console.cloud.google.com/)
2. Activer l'API Google Calendar
3. Créer des identifiants OAuth 2.0
4. Récupérer `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET`

## 🚀 Démarrage

### Backend
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm run dev
```

L'application sera accessible sur :
- Frontend : http://localhost:3000
- Backend API : http://localhost:8000
- Documentation API : http://localhost:8000/docs

## 📁 Structure du Projet

```
athletIQ/
├── backend/                 # API FastAPI
│   ├── app/
│   │   ├── api/            # Routes API
│   │   ├── auth/           # Authentification
│   │   ├── core/           # Configuration
│   │   └── domain/         # Logique métier
│   ├── alembic/            # Migrations DB
│   └── requirements.txt
├── frontend/               # Application React
│   ├── src/
│   │   ├── components/     # Composants React
│   │   ├── pages/          # Pages de l'application
│   │   └── services/       # Services API
│   └── package.json
├── docs/                   # Documentation
└── scripts/                # Scripts utilitaires
```

## 🔧 Configuration

### Variables d'environnement Backend (.env)

```env
# Base de données
DATABASE_URL=sqlite:///./stridedelta.db

# JWT
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256

# Strava
STRAVA_CLIENT_ID=your-strava-client-id
STRAVA_CLIENT_SECRET=your-strava-client-secret
STRAVA_REFRESH_TOKEN=your-strava-refresh-token

# Google
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Sécurité
ENCRYPTION_KEY=your-encryption-key
```

### Variables d'environnement Frontend (.env)

```env
VITE_API_URL=http://localhost:8000/api/v1
VITE_STRAVA_CLIENT_ID=your-strava-client-id
```

## 🧪 Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

## 📚 Documentation

- [Guide de démarrage](GUIDE_DEMARRAGE_ATHLETIQ.md)
- [Configuration détaillée](README-CONFIGURATION.md)
- [Documentation API](docs/api.md)
- [Architecture](docs/architecture.md)

## Webhooks Strava

athletIQ utilise les webhooks Strava pour recevoir les nouvelles activites en temps reel (creation, modification, suppression). Cela evite de devoir synchroniser manuellement.

### Pre-requis

- L'application backend doit etre deployee et accessible publiquement (HTTPS requis par Strava)
- Avoir un `STRAVA_CLIENT_ID` et un `STRAVA_CLIENT_SECRET` valides
- Avoir un access token Strava avec le scope `read` (ou `read_all`)

### Etape 1 : Configurer les variables d'environnement

Dans le `.env` du backend, definir :

```env
# Token aleatoire de votre choix, utilise pour valider la subscription
STRAVA_WEBHOOK_VERIFY_TOKEN=<choisir-un-token-aleatoire-fort>
```

### Etape 2 : Enregistrer la subscription webhook

Depuis un terminal, envoyer la requete suivante a l'API Strava :

```bash
curl -X POST https://www.strava.com/api/v3/push_subscriptions \
  -F client_id=<VOTRE_STRAVA_CLIENT_ID> \
  -F client_secret=<VOTRE_STRAVA_CLIENT_SECRET> \
  -F callback_url=https://<VOTRE_DOMAINE_BACKEND>/api/v1/webhooks/strava \
  -F verify_token=<LE_MEME_TOKEN_QUE_STRAVA_WEBHOOK_VERIFY_TOKEN>
```

Strava va envoyer un `GET` a votre `callback_url` avec un challenge. Le backend repond automatiquement si le `verify_token` correspond.

En cas de succes, Strava retourne un JSON avec un `id` (subscription ID) :

```json
{"id": 328992}
```

### Etape 3 : Configurer le subscription ID

Ajouter l'ID retourne dans le `.env` du backend :

```env
STRAVA_WEBHOOK_SUBSCRIPTION_ID=328992
```

Cela permet au backend de rejeter les evenements provenant d'une subscription inconnue.

### Verification

Pour verifier que la subscription est active :

```bash
curl -G https://www.strava.com/api/v3/push_subscriptions \
  -d client_id=<VOTRE_STRAVA_CLIENT_ID> \
  -d client_secret=<VOTRE_STRAVA_CLIENT_SECRET>
```

### Suppression

Pour supprimer une subscription existante :

```bash
curl -X DELETE "https://www.strava.com/api/v3/push_subscriptions/<SUBSCRIPTION_ID>" \
  -F client_id=<VOTRE_STRAVA_CLIENT_ID> \
  -F client_secret=<VOTRE_STRAVA_CLIENT_SECRET>
```

### Notes importantes

- Strava n'autorise qu'**une seule subscription** par application. Pour en creer une nouvelle, supprimer l'ancienne d'abord.
- Le backend doit repondre au challenge GET **sous 2 secondes**. Si l'app est sur un service free-tier (ex: Render free), le cold start peut faire echouer la premiere tentative. Reveiller le service (via `/health`) avant de lancer l'enregistrement.
- Les evenements POST sont traites en arriere-plan (fire-and-forget) pour garantir la reponse HTTP 200 sous 2 secondes.
- Les types d'evenements geres : `activity.create`, `activity.update`, `activity.delete`.
- Sur `activity.create`, l'activite est automatiquement ajoutee dans la file d'enrichissement.

## 🤝 Contribution

1. Fork le projet
2. Créer une branche feature (`git checkout -b feature/AmazingFeature`)
3. Commit les changements (`git commit -m 'Add some AmazingFeature'`)
4. Push vers la branche (`git push origin feature/AmazingFeature`)
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

## 🆘 Support

Pour toute question ou problème :
- Ouvrir une issue sur GitHub
- Consulter la [documentation](docs/)
- Vérifier les [guides de dépannage](docs/)

## 🔒 Sécurité

⚠️ **Important** : Ne jamais commiter les fichiers `.env` contenant vos vraies clés API. Utilisez toujours les fichiers `.env.example` comme modèles. 