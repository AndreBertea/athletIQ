import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // `autoUpdate` : le SW se met à jour silencieusement au prochain
      // chargement (pas de prompt utilisateur). Crucial pour les
      // itérations rapides en démo où on push plusieurs fois par heure.
      // Sinon le SW garde l'ancien CSS / JS et les fix CSS (ex. safe-area)
      // ne s'appliquent jamais sans désinstall manuelle de la PWA.
      registerType: 'autoUpdate',
      // L'enregistrement est fait explicitement dans src/main.tsx pour
      // forcer registration.update() à l'ouverture de la PWA. L'injection
      // automatique génère un registerSW.js trop passif pour les itérations
      // rapides de la bêta mobile.
      injectRegister: null,
      // On gère manuellement public/manifest.json (statique) plutôt que
      // de laisser le plugin générer un manifest.webmanifest. Évite le
      // double manifest et garde l'index.html en source de vérité.
      manifest: false,
      includeAssets: ['icon-192.svg', 'icon-512.svg', 'manifest.json'],
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
      // Dev SW désactivé : on évite les caches parasites pendant le hot reload.
      // À activer ponctuellement (devOptions.enabled = true) pour tester
      // l'install PWA en local.
      devOptions: {
        enabled: false,
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // Port 5173 (Vite default) — IMPORTANT : pas 4000 qui est déjà
    // occupé par le frontend AGON existant.
    port: 5173,
    host: true,
    proxy: {
      // Forward des appels API vers le backend FastAPI (port 8000).
      // `ws: true` pour gérer le WebSocket utilisé par Live tracking.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
