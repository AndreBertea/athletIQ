# Guide de configuration Google Calendar pour Stridelta

## Étape 1 : Créer un projet Google Cloud

1. **Aller sur Google Cloud Console**
   - Ouvrir [https://console.cloud.google.com/](https://console.cloud.google.com/)
   - Se connecter avec votre compte Google

2. **Créer un nouveau projet**
   - Cliquer sur le sélecteur de projet en haut à gauche
   - Cliquer sur "Nouveau projet"
   - Nom du projet : `stridelta-calendar`
   - Cliquer sur "Créer"

3. **Sélectionner le projet**
   - Une fois créé, sélectionner le projet `stridelta-calendar`

## Étape 2 : Activer l'API Google Calendar

1. **Aller dans les APIs et services**
   - Menu latéral → "APIs et services" → "Bibliothèque"

2. **Rechercher et activer Google Calendar API**
   - Rechercher "Google Calendar API"
   - Cliquer sur "Google Calendar API"
   - Cliquer sur "Activer"

## Étape 3 : Configurer les identifiants OAuth

1. **Aller dans les identifiants**
   - Menu latéral → "APIs et services" → "Identifiants"

2. **Créer un identifiant OAuth 2.0**
   - Cliquer sur "Créer des identifiants"
   - Sélectionner "ID client OAuth 2.0"

3. **Configurer l'écran de consentement**
   - Si demandé, configurer l'écran de consentement :
     - Type d'utilisateur : "Externe"
     - Nom de l'application : "Stridelta"
     - Email de support : votre email
     - Domaine de l'application : `localhost` (pour le développement)

4. **Créer l'ID client**
   - Type d'application : "Application Web"
   - Nom : "Stridelta Calendar Integration"
   - URIs de redirection autorisés :
     - `http://localhost:8000/api/v1/auth/google/callback` (développement)
     - `https://votre-domaine.com/api/v1/auth/google/callback` (production)

5. **Récupérer les identifiants**
   - Noter le **Client ID** et le **Client Secret** (exemple: 123456789-abcdefghijklmnop.apps.googleusercontent.com)
   - Ces informations seront nécessaires pour la configuration

## Étape 4 : Configurer les variables d'environnement

1. **Créer un fichier `.env` dans le dossier backend**

```bash
# Configuration Google Calendar OAuth pour Stridelta
GOOGLE_CLIENT_ID=your_google_client_id_here
GOOGLE_CLIENT_SECRET=your_google_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback

# Clé de chiffrement pour les tokens (générer une clé sécurisée)
ENCRYPTION_KEY=your_secure_encryption_key_here

# Configuration existante
DATABASE_URL=sqlite:///./stridedelta.db
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Strava OAuth (configuration existante)
STRAVA_CLIENT_ID=158144
STRAVA_CLIENT_SECRET=your_strava_client_secret_here
STRAVA_REFRESH_TOKEN=your_strava_refresh_token_here
STRAVA_REDIRECT_URI=http://localhost:8000/api/v1/auth/strava/callback

# CORS
ALLOWED_ORIGINS=["*"]

# Application
DEBUG=True
ENVIRONMENT=development
```

## Étape 5 : Générer une clé de chiffrement sécurisée

1. **Ouvrir un terminal Python**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

2. **Copier la clé générée**
   - Remplacer `your_secure_encryption_key_here` par la clé générée

## Étape 6 : Remplacer les valeurs dans le fichier .env

1. **Remplacer les valeurs par vos identifiants Google**
   - `your_google_client_id_here` → Votre Client ID Google
   - `your_google_client_secret_here` → Votre Client Secret Google
   - `your_secure_encryption_key_here` → Votre clé de chiffrement

## Étape 7 : Redémarrer le backend

1. **Arrêter le backend actuel**
```bash
pkill -f uvicorn
```

2. **Redémarrer avec la nouvelle configuration**
```bash
cd backend && ./start_backend_optimized.sh
```

## Étape 8 : Tester la connexion

1. **Ouvrir l'application Stridelta**
2. **Aller sur la page des plans d'entraînement**
3. **Cliquer sur le bouton "Google Calendar"**
4. **Suivre le processus d'autorisation Google**

## Configuration pour la production

Pour la production, modifier les URIs de redirection dans Google Cloud Console :

1. **Aller dans Google Cloud Console**
2. **APIs et services → Identifiants**
3. **Modifier l'ID client OAuth 2.0**
4. **Ajouter l'URI de production** :
   - `https://votre-domaine.com/api/v1/auth/google/callback`

5. **Mettre à jour le fichier .env de production** :
```bash
GOOGLE_REDIRECT_URI=https://votre-domaine.com/api/v1/auth/google/callback
```

## Permissions requises

L'application Stridelta demande les permissions suivantes :
- **Lire les calendriers** : Pour importer les événements d'entraînement
- **Écrire dans les calendriers** : Pour exporter les plans d'entraînement

## Dépannage

### Erreur "Missing required parameter: client_id"
- Vérifier que `GOOGLE_CLIENT_ID` est bien configuré dans le fichier `.env`
- Redémarrer le backend après modification

### Erreur "Invalid redirect URI"
- Vérifier que l'URI de redirection dans Google Cloud Console correspond à `GOOGLE_REDIRECT_URI`
- Pour le développement : `http://localhost:8000/api/v1/auth/google/callback`

### Erreur de chiffrement
- Vérifier que `ENCRYPTION_KEY` est bien configuré
- Régénérer une nouvelle clé si nécessaire

## Sécurité

- **Ne jamais commiter le fichier `.env`** dans Git
- **Utiliser des clés différentes** pour développement et production
- **Régénérer régulièrement** les clés de chiffrement
- **Limiter les permissions** aux calendriers nécessaires uniquement 