# Intégration Google Calendar pour Stridelta

## Vue d'ensemble

Stridelta intègre Google Calendar pour permettre aux utilisateurs de :
- **Exporter** leurs plans d'entraînement vers Google Calendar
- **Importer** des événements d'entraînement depuis Google Calendar

## Fonctionnalités

### Export vers Google Calendar
- Export automatique des plans d'entraînement
- Création d'événements avec détails (type, distance, allure, etc.)
- Rappels automatiques 30 minutes avant l'entraînement
- Couleurs différentes selon le type d'entraînement

### Import depuis Google Calendar
- Import des événements contenant des mots-clés d'entraînement
- Détection automatique du type d'entraînement
- Conversion en plans d'entraînement Stridelta
- Éviter les doublons

## Architecture

### Backend (FastAPI)
- **Service OAuth Google** : Gestion de l'authentification
- **Service Google Calendar** : API pour lire/écrire les calendriers
- **Entité GoogleAuth** : Stockage sécurisé des tokens
- **Routes API** : Endpoints pour l'export/import

### Frontend (React)
- **Page GoogleConnect** : Gestion de la connexion OAuth
- **Modal GoogleCalendar** : Interface pour l'export/import
- **Service Google Calendar** : Appels API vers le backend

## Configuration requise

### Variables d'environnement
```bash
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
ENCRYPTION_KEY=your_secure_encryption_key
```

### Base de données
- Table `googleauth` pour stocker les tokens utilisateur
- Relation avec la table `user`

## Installation et configuration

### 1. Configuration Google Cloud
Suivre le guide complet : [Configuration Google Calendar](configuration-google-calendar.md)

### 2. Génération de la clé de chiffrement
```bash
python3 scripts/generate-encryption-key.py
```

### 3. Test de la configuration
```bash
python3 scripts/test-google-config.py
```

## Utilisation

### Pour l'utilisateur final

1. **Connexion Google**
   - Cliquer sur "Connexion Google" dans l'application
   - Autoriser l'accès aux calendriers
   - Retour automatique à l'application

2. **Export vers Google Calendar**
   - Aller sur la page des plans d'entraînement
   - Cliquer sur "Google Calendar"
   - Sélectionner le calendrier de destination
   - Confirmer l'export

3. **Import depuis Google Calendar**
   - Cliquer sur "Importer depuis Google"
   - Sélectionner le calendrier source
   - Choisir la période d'import
   - Confirmer l'import

### Pour le développeur

#### Routes API disponibles
```bash
# Connexion OAuth
GET /api/v1/auth/google/login
GET /api/v1/auth/google/callback
GET /api/v1/auth/google/status

# Gestion des calendriers
GET /api/v1/google-calendar/calendars
POST /api/v1/google-calendar/export
POST /api/v1/google-calendar/import
```

#### Exemple d'utilisation
```bash
# Récupérer les calendriers
curl -X GET "http://localhost:8000/api/v1/google-calendar/calendars" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Exporter vers Google Calendar
curl -X POST "http://localhost:8000/api/v1/google-calendar/export" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"calendar_id": "primary"}'

# Importer depuis Google Calendar
curl -X POST "http://localhost:8000/api/v1/google-calendar/import" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"calendar_id": "primary", "start_date": "2025-01-01", "end_date": "2025-01-31"}'
```

## Sécurité

### Chiffrement des tokens
- Les tokens Google sont chiffrés avant stockage en base
- Utilisation de Fernet (cryptography) pour le chiffrement
- Clé de chiffrement configurable via `ENCRYPTION_KEY`

### Permissions OAuth
- Accès limité aux calendriers uniquement
- Pas d'accès aux emails ou autres données Google
- Tokens avec expiration automatique

### Gestion des erreurs
- Gestion des tokens expirés
- Actualisation automatique des refresh tokens
- Messages d'erreur explicites pour l'utilisateur

## Dépannage

### Erreurs courantes

#### "Missing required parameter: client_id"
- Vérifier la configuration `GOOGLE_CLIENT_ID`
- Redémarrer le backend après modification

#### "Invalid redirect URI"
- Vérifier `GOOGLE_REDIRECT_URI` dans Google Cloud Console
- S'assurer que l'URI correspond exactement

#### "Access denied"
- Vérifier les permissions dans Google Cloud Console
- S'assurer que l'API Calendar est activée

#### Erreurs de chiffrement
- Régénérer la clé de chiffrement
- Vérifier le format de `ENCRYPTION_KEY`

### Logs de débogage
```bash
# Activer les logs détaillés
cd backend
uvicorn app.main:app --log-level debug
```

## Développement

### Structure des fichiers
```
backend/
├── app/
│   ├── auth/
│   │   └── google_oauth.py          # Service OAuth Google
│   ├── domain/
│   │   ├── entities/
│   │   │   └── user.py              # Entité GoogleAuth
│   │   └── services/
│   │       └── google_calendar_service.py  # Service Calendar
│   └── api/
│       └── routes.py                # Routes API Google
frontend/
├── src/
│   ├── pages/
│   │   └── GoogleConnect.tsx        # Page de connexion
│   ├── components/
│   │   └── GoogleCalendarModal.tsx  # Modal Calendar
│   └── services/
│       └── googleCalendarService.ts # Service frontend
```

### Tests
```bash
# Test de la configuration
python3 scripts/test-google-config.py

# Test des routes API
curl -X GET "http://localhost:8000/api/v1/google-calendar/calendars" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Production

### Configuration
- Utiliser des URIs de redirection HTTPS
- Configurer des clés de chiffrement différentes
- Limiter les origines CORS

### Monitoring
- Surveiller les erreurs OAuth
- Tracer les exports/imports
- Monitorer l'utilisation de l'API Google

### Sécurité
- Rotation régulière des clés
- Audit des permissions
- Logs de sécurité

## Support

Pour toute question ou problème :
1. Consulter ce guide
2. Vérifier la configuration
3. Consulter les logs du backend
4. Tester avec les scripts fournis

## Changelog

### Version 1.0.0
- Intégration initiale Google Calendar
- Export/import des plans d'entraînement
- Interface utilisateur complète
- Sécurité OAuth 2.0 