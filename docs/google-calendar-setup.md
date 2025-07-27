# Configuration Google Calendar - AthletIQ

## 🎯 Vue d'ensemble

Cette fonctionnalité permet de synchroniser vos plans d'entraînement avec Google Calendar :

- **Export** : Vos plans d'entraînement sont exportés vers Google Calendar
- **Import** : Les événements de Google Calendar sont importés comme plans d'entraînement

## 🔧 Configuration Backend

### 1. Créer un projet Google Cloud

1. Allez sur [Google Cloud Console](https://console.cloud.google.com/)
2. Créez un nouveau projet ou sélectionnez un projet existant
3. Activez l'API Google Calendar :
   - Menu → APIs & Services → Library
   - Recherchez "Google Calendar API"
   - Cliquez sur "Enable"

### 2. Configurer les credentials OAuth

1. Menu → APIs & Services → Credentials
2. Cliquez sur "Create Credentials" → "OAuth 2.0 Client IDs"
3. Configurez l'écran de consentement OAuth :
   - User Type : External
   - App name : AthletIQ
   - User support email : votre email
   - Developer contact information : votre email
   - Scopes : ajoutez `https://www.googleapis.com/auth/calendar`

4. Créez les credentials OAuth :
   - Application type : Web application
   - Name : AthletIQ Web Client
   - Authorized redirect URIs : `http://localhost:8000/api/v1/auth/google/callback`

### 3. Configurer les variables d'environnement

Ajoutez ces variables dans votre fichier `.env` :

```bash
# Google Calendar OAuth
GOOGLE_CLIENT_ID=votre-client-id-google
GOOGLE_CLIENT_SECRET=votre-client-secret-google
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/google/callback
```

## 🚀 Utilisation

### Connexion Google Calendar

1. Allez sur la page des plans d'entraînement
2. Cliquez sur le bouton "Google Calendar"
3. Cliquez sur "Se connecter avec Google"
4. Autorisez l'accès à votre compte Google
5. Vous serez redirigé vers les plans d'entraînement

### Export vers Google Calendar

1. Ouvrez le modal Google Calendar
2. Sélectionnez le calendrier de destination
3. Cliquez sur "Exporter les plans d'entraînement"
4. Vos plans seront créés comme événements dans Google Calendar

### Import depuis Google Calendar

1. Ouvrez le modal Google Calendar
2. Sélectionnez le calendrier source
3. Optionnellement, définissez une période (dates de début/fin)
4. Cliquez sur "Importer depuis le calendrier"
5. Les événements d'entraînement seront importés comme plans

## 🔍 Détection automatique des entraînements

L'import détecte automatiquement les événements d'entraînement en cherchant ces mots-clés :

- **Course** : course, running, jogging, entraînement, training, sport
- **Émojis** : 🏃‍♂️, 🏃
- **Types spécifiques** : run, cardio, endurance, interval, tempo

### Types d'entraînement détectés

- **Intervalles** : interval, intervalles, fractionné
- **Tempo** : tempo, seuil
- **Sortie longue** : longue, long, endurance
- **Récupération** : récupération, recovery, facile
- **Fartlek** : fartlek
- **Côtes** : côte, hill, montée
- **Course** : course, race, compétition
- **Course facile** : par défaut

## 📊 Extraction des données

L'import extrait automatiquement ces informations de la description :

- **Distance** : `10km`, `5.5 km`
- **Dénivelé** : `+150m`, `+200 m`
- **Allure** : `4:30/km`, `5:15/km`

## 🎨 Couleurs Google Calendar

Les événements exportés utilisent un code couleur selon le type d'entraînement :

- **Course facile** : Bleu
- **Intervalles** : Rouge
- **Tempo** : Orange
- **Sortie longue** : Vert
- **Récupération** : Gris
- **Fartlek** : Violet
- **Côtes** : Jaune
- **Course** : Rose

## 🔒 Sécurité

- Les tokens Google sont chiffrés avant stockage
- Seuls les calendriers avec permissions d'écriture sont utilisés
- Les tokens sont automatiquement actualisés quand ils expirent

## 🐛 Dépannage

### Erreur "Google Calendar non connecté"

1. Vérifiez que vous êtes connecté à Google Calendar
2. Allez sur `/google-connect` pour vous reconnecter
3. Vérifiez les variables d'environnement

### Erreur "Quota exceeded"

- L'API Google Calendar a des limites quotidiennes
- Attendez 24h ou contactez le support Google

### Événements non importés

- Vérifiez que les événements contiennent des mots-clés d'entraînement
- Ajoutez des mots-clés dans le titre ou la description
- Vérifiez les permissions du calendrier

## 📝 Exemples d'événements Google Calendar

### Événement simple
```
Titre : 🏃‍♂️ Course facile
Description : 5km à allure confortable
```

### Événement détaillé
```
Titre : Intervalles 400m
Description : 
10x400m avec 200m récupération
Distance: 6km
Dénivelé: +50m
Allure: 4:00/km
```

### Événement avec notes
```
Titre : Sortie longue
Description : 
Endurance de base - 15km
Notes du coach: Garder une allure régulière
Distance: 15km
Dénivelé: +200m
``` 