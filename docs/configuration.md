# Configuration d'AthletIQ

## 📋 Variables d'environnement requises

### Backend (.env)

```bash
# Configuration de la base de données
DATABASE_URL=postgresql://stridedelta_user:stridedelta_pass@localhost:5432/stridedelta_dev

# Configuration JWT
JWT_SECRET_KEY=ZPCtStH03EuCXVjaehZBgcRTqMBcEqO_TgsaRvil_H0
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Configuration Strava OAuth
STRAVA_CLIENT_ID=158144
STRAVA_CLIENT_SECRET=your-strava-client-secret-here
STRAVA_REDIRECT_URI=http://localhost:8000/api/v1/auth/strava/callback

# Configuration de chiffrement
ENCRYPTION_KEY=awpNHGbkbn_3M6X8fi7GkWU68QURefKDb48Qpxu7_f0=

# Configuration CORS
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173"]

# Configuration de l'application
DEBUG=true
ENVIRONMENT=development
```

### Frontend (.env)

```bash
# Configuration de l'API
VITE_API_URL=http://localhost:8000/api/v1

# Configuration Strava (optionnel)
VITE_STRAVA_CLIENT_ID=158144
```

## 🔑 Obtenir les credentials Strava

1. **Allez sur** https://www.strava.com/settings/api
2. **Connectez-vous** à votre compte Strava
3. **Créez une nouvelle application** :
   - Nom de l'application : `AthletIQ`
   - Catégorie : `Analytics`
   - Description : `Application d'analyse de performances sportives`
4. **Notez** :
   - Client ID (déjà configuré : 158144)
   - Client Secret (à copier dans `STRAVA_CLIENT_SECRET`)

## 🚀 Démarrage rapide

### 1. Configurer les variables d'environnement

```bash
# Copier le fichier .env.example
cp backend/.env.example backend/.env

# Éditer avec vos vraies valeurs
nano backend/.env
```

### 2. Lancer la base de données

```bash
docker-compose -f docker-compose.dev.yml up postgres -d
```

### 3. Lancer le backend

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### 4. Lancer le frontend

```bash
cd frontend
npm run dev
```

## 🔒 Sécurité

### Clés à générer

**JWT Secret Key :**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Encryption Key :**
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Variables sensibles

⚠️ **NE JAMAIS COMMITER** :
- `JWT_SECRET_KEY`
- `STRAVA_CLIENT_SECRET`
- `ENCRYPTION_KEY`
- `DATABASE_URL` (en production)

## 🌐 URLs d'accès

- **Frontend** : http://localhost:3000
- **Backend API** : http://localhost:8000
- **Documentation API** : http://localhost:8000/docs
- **Base de données** : localhost:5432

## 📊 Base de données

**Credentials par défaut :**
- Database : `stridedelta_dev`
- User : `stridedelta_user`
- Password : `stridedelta_pass`
- Port : `5432`

## 🔧 Dépannage

### Erreur de connexion à la base de données
```bash
# Vérifier que PostgreSQL est lancé
docker-compose -f docker-compose.dev.yml ps

# Redémarrer si nécessaire
docker-compose -f docker-compose.dev.yml restart postgres
```

### Erreur JWT
```bash
# Vérifier que JWT_SECRET_KEY est défini
echo $JWT_SECRET_KEY

# Régénérer si nécessaire
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Erreur Strava OAuth
1. Vérifier que `STRAVA_CLIENT_SECRET` est correct
2. Vérifier que l'URL de callback correspond à votre configuration
3. Vérifier que l'application Strava est bien configurée 