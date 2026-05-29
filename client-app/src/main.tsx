import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from 'next-themes';
import { registerSW } from 'virtual:pwa-register';

// Loading order matters — see web/src/styles/globals.css header.
import './styles/design-system.css';
import './styles/globals.css';

// i18n — initialise i18next + détecteur localStorage/navigator avant le
// premier render. Tout `useTranslation()` profite immédiatement de la
// langue résolue (FR par défaut, EN si choix utilisateur ou navigateur).
import './i18n';

import App from './App';
import { ThemedToaster } from './components/shared/ThemedToaster';

const updateServiceWorker = registerSW({
  immediate: true,
  onNeedRefresh() {
    void updateServiceWorker(true);
  },
  onRegisteredSW(_swUrl, registration) {
    if (!registration) return;
    void registration.update();
    window.setInterval(() => {
      void registration.update();
    }, 5 * 60 * 1000);
  },
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// Clé de persistance du thème — partagée avec le script anti-FOUC dans
// index.html. Toute modification ici doit y être répercutée.
const THEME_STORAGE_KEY = 'agon-theme';

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root missing from index.html');

createRoot(rootEl).render(
  <StrictMode>
    <ThemeProvider
      attribute="data-theme"
      defaultTheme="dark"
      enableSystem
      themes={['light', 'dark']}
      storageKey={THEME_STORAGE_KEY}
      disableTransitionOnChange
    >
      <QueryClientProvider client={queryClient}>
        <App />
        <ThemedToaster />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
