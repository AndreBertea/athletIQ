# Configuration TypeScript avec Vite - AthlétIQ

## Problème : Erreur TypeScript avec `import.meta.env`

### Symptômes
- Erreur rouge sous `import.meta.env.VITE_API_URL`
- TypeScript ne reconnaît pas les variables d'environnement Vite
- Erreur : `Property 'VITE_API_URL' does not exist on type 'ImportMetaEnv'`

### Solution

#### 1. Fichier de Déclaration de Types

Créez le fichier `frontend/src/vite-env.d.ts` :

```typescript
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_DEV_MODE: string
  // Ajoutez d'autres variables d'environnement ici si nécessaire
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

#### 2. Configuration TypeScript

Fichier `frontend/tsconfig.json` :

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    /* Bundler mode */
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",

    /* Linting */
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,

    /* Path mapping */
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },

    /* Type checking */
    "types": ["vite/client"]
  },
  "include": [
    "src",
    "src/**/*",
    "src/vite-env.d.ts"
  ],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

#### 3. Configuration Node.js

Fichier `frontend/tsconfig.node.json` :

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

#### 4. Configuration ESLint

Fichier `frontend/.eslintrc.js` :

```javascript
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    '@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.js'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    // Désactiver l'erreur pour import.meta.env
    '@typescript-eslint/no-explicit-any': 'off',
  },
}
```

## Utilisation des Variables d'Environnement

### Syntaxe Correcte

```typescript
// ✅ Correct
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

// ❌ Incorrect (ancienne syntaxe)
const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || '/api/v1'
```

### Variables Disponibles

Dans `vite-env.d.ts`, déclarez toutes vos variables d'environnement :

```typescript
interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_DEV_MODE: string
  readonly VITE_APP_TITLE: string
  readonly VITE_STRIPE_PUBLIC_KEY: string
  // etc.
}
```

### Fichier d'Environnement

Créez un fichier `.env.local` dans le répertoire `frontend/` :

```bash
# Configuration de l'API
VITE_API_URL=/api/v1

# Configuration de développement
VITE_DEV_MODE=true
VITE_APP_TITLE=AthlétIQ
```

## Redémarrage Nécessaire

Après avoir modifié les fichiers de configuration TypeScript :

1. **Arrêter le serveur de développement :**
   ```bash
   # Dans le terminal où le frontend tourne
   Ctrl+C
   ```

2. **Redémarrer le serveur :**
   ```bash
   cd frontend
   npm run dev
   ```

3. **Vérifier que l'erreur a disparu :**
   - L'erreur rouge sous `import.meta.env.VITE_API_URL` devrait disparaître
   - L'autocomplétion devrait fonctionner

## Vérification

### Test de la Configuration

```typescript
// Dans un fichier TypeScript
console.log(import.meta.env.VITE_API_URL) // Devrait être reconnu sans erreur
```

### Script de Test

Utilisez le script de test pour vérifier que tout fonctionne :

```bash
./scripts/test-connection.sh
```

## Dépannage

### Erreur Persistante

Si l'erreur persiste après redémarrage :

1. **Vérifier les fichiers de configuration :**
   ```bash
   ls -la frontend/tsconfig*.json
   ls -la frontend/src/vite-env.d.ts
   ```

2. **Nettoyer le cache :**
   ```bash
   cd frontend
   rm -rf node_modules/.vite
   npm run dev
   ```

3. **Vérifier les dépendances :**
   ```bash
   cd frontend
   npm install
   ```

### Erreur de Module

Si vous avez une erreur de module non trouvé :

1. **Vérifier que Vite est installé :**
   ```bash
   cd frontend
   npm list vite
   ```

2. **Réinstaller les dépendances :**
   ```bash
   cd frontend
   rm -rf node_modules package-lock.json
   npm install
   ```

## Bonnes Pratiques

1. **Toujours déclarer les variables dans `vite-env.d.ts`**
2. **Utiliser le préfixe `VITE_` pour toutes les variables d'environnement**
3. **Redémarrer le serveur après modification des fichiers de configuration**
4. **Utiliser des valeurs par défaut pour les variables d'environnement**
5. **Ne jamais commiter les fichiers `.env.local` dans Git** 