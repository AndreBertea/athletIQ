# 🎯 Première utilisation d'AthletIQ

## 📋 Résumé

**Oui, lors du premier lancement, vous devez créer un compte !** 

Votre application AthletIQ utilise un système d'authentification complet avec JWT. Il n'y a pas d'utilisateur par défaut pour des raisons de sécurité.

## 🚀 Options pour commencer

### Option 1 : Créer un compte normal (recommandé)

1. **Lancez l'application** :
   ```bash
   # Base de données
   docker compose -f docker-compose.dev.yml up postgres -d
   
   # Backend
   cd backend && python -m uvicorn app.main:app --reload
   
   # Frontend
   cd frontend && npm run dev
   ```

2. **Allez sur** http://localhost:3002 (ou le port affiché par Vite)

3. **Cliquez sur "Créer un nouveau compte"**

4. **Remplissez le formulaire** :
   - Nom complet : Votre nom
   - Email : Votre email
   - Mot de passe : Au moins 6 caractères

5. **Connectez-vous** avec vos credentials

### Option 2 : Utiliser l'utilisateur de test (développement)

```bash
# Créer automatiquement un utilisateur de test
./scripts/create-test-user.sh
```

**Credentials automatiques :**
- Email : `test@athletiq.com`
- Mot de passe : `test123456`

## 🔐 Authentification

### Fonctionnalités disponibles

- ✅ **Inscription** : Créer un nouveau compte
- ✅ **Connexion** : Se connecter avec email/mot de passe
- ✅ **JWT Tokens** : Authentification sécurisée
- ✅ **Refresh Token** : Reconnexion automatique
- 🔄 **Strava OAuth** : Connexion avec Strava (à configurer)

### Sécurité

- Les mots de passe sont hashés avec bcrypt
- Les tokens JWT expirent automatiquement
- Les tokens Strava sont chiffrés en base de données

## 📱 Interface utilisateur

### Page de connexion

- **Onglet Connexion** : Pour les utilisateurs existants
- **Onglet Inscription** : Pour créer un nouveau compte
- **Validation en temps réel** : Vérification des champs
- **Gestion d'erreurs** : Messages d'erreur clairs

### Après connexion

- **Dashboard** : Vue d'ensemble de vos activités
- **Profil** : Gestion de votre compte
- **Intégration Strava** : Connexion à votre compte Strava
- **Plans d'entraînement** : Création et suivi

## 🔧 Configuration Strava (optionnel)

Après avoir créé votre compte, vous pouvez :

1. **Connecter votre compte Strava** :
   - Cliquez sur "Connecter Strava"
   - Autorisez l'accès à vos activités
   - Synchronisez vos données

2. **Configurer les permissions** :
   - Lecture des activités
   - Accès aux données de performance
   - Synchronisation automatique

## 🆘 Dépannage

### Erreur de connexion

```bash
# Vérifier que le backend fonctionne
curl http://localhost:8000/health

# Vérifier la base de données
docker compose -f docker-compose.dev.yml ps
```

### Mot de passe oublié

Pour le moment, il n'y a pas de récupération de mot de passe. Vous devrez :
1. Créer un nouveau compte avec un autre email
2. Ou supprimer la base de données et recommencer

### Problème de base de données

```bash
# Redémarrer PostgreSQL
docker compose -f docker-compose.dev.yml restart postgres

# Vérifier les logs
docker compose -f docker-compose.dev.yml logs postgres
```

## 📚 Prochaines étapes

1. **Explorez le dashboard** : Découvrez les fonctionnalités
2. **Connectez Strava** : Synchronisez vos activités
3. **Créez des plans** : Planifiez vos entraînements
4. **Analysez vos performances** : Suivez vos progrès

## 🎯 Conseils

- **Utilisez un email valide** : Pour la récupération future
- **Choisissez un mot de passe fort** : Au moins 8 caractères
- **Sauvegardez vos credentials** : Notez-les quelque part
- **Testez l'application** : Explorez toutes les fonctionnalités

---

**🎉 Bienvenue dans AthletIQ ! Votre assistant sport IA est prêt à vous accompagner !** 