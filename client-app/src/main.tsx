import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';

// Loading order matters — see web/src/styles/globals.css header.
import './styles/design-system.css';
import './styles/globals.css';

// i18n — initialise i18next + détecteur localStorage/navigator avant le
// premier render. Tout `useTranslation()` profite immédiatement de la
// langue résolue (FR par défaut, EN si choix utilisateur ou navigateur).
import './i18n';

import App from './App';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root missing from index.html');

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster
        position="top-center"
        theme="dark"
        toastOptions={{
          classNames: {
            toast:
              'bg-card border border-border-subtle text-foreground font-text',
            description: 'text-muted-foreground',
          },
        }}
      />
    </QueryClientProvider>
  </StrictMode>,
);
