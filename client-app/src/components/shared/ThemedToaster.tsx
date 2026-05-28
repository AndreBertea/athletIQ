/**
 * ThemedToaster — Toaster sonner dont le thème suit le thème résolu de
 * l'app (dark/light, incluant "Système" via next-themes). Synchronise
 * aussi `<meta name="theme-color">` pour que la barre d'état du navigateur
 * / PWA s'accorde à la surface dominante.
 *
 * Doit être monté SOUS le ThemeProvider (accès à useTheme()).
 */

import { useEffect } from 'react';
import { useTheme } from 'next-themes';
import { Toaster } from 'sonner';

const THEME_COLORS = {
  light: '#F5EFE0', // ivoire chaud
  dark: '#191815', // deep night
} as const;

export function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  const mode = resolvedTheme === 'light' ? 'light' : 'dark';

  useEffect(() => {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', THEME_COLORS[mode]);
  }, [mode]);

  return (
    <Toaster
      position="top-center"
      theme={mode}
      toastOptions={{
        classNames: {
          toast: 'bg-card border border-border-subtle text-foreground font-text',
          description: 'text-muted-foreground',
        },
      }}
    />
  );
}

export default ThemedToaster;
