/**
 * Accent commutable AGON.
 *
 * Le violet pur du logo (--spark) reste l'etincelle dans tous les cas ;
 * seule la couleur de TRAVAIL (--action : boutons / CTA / onglet actif /
 * liens) change. Pilote via l'attribut `data-accent` sur <html>, lu aussi
 * par le script anti-FOUC d'index.html (meme cle localStorage).
 *
 * Defaut = "amethyste" (prune desature, cousin du logo). Les valeurs
 * concretes (hex dark/light) vivent dans src/styles/design-system.css
 * sous :root / [data-theme="light"] / [data-accent="..."].
 */

export const ACCENTS = ['amethyste', 'aubergine', 'braise'] as const;
export type Accent = (typeof ACCENTS)[number];

export const ACCENT_STORAGE_KEY = 'agon-accent';

/** Libelle + pastille (hex dark, pour l'apercu dans le selecteur). */
export const ACCENT_META: Record<Accent, { label: string; swatch: string }> = {
  amethyste: { label: 'Améthyste', swatch: '#7E4FA6' },
  aubergine: { label: 'Aubergine', swatch: '#7A4A6E' },
  braise: { label: 'Braise', swatch: '#BE5638' },
};

function isAccent(value: string | null): value is Accent {
  return value === 'amethyste' || value === 'aubergine' || value === 'braise';
}

export function getAccent(): Accent {
  try {
    const stored = localStorage.getItem(ACCENT_STORAGE_KEY);
    if (isAccent(stored)) return stored;
  } catch {
    /* localStorage indisponible (SSR / mode prive) → defaut */
  }
  return 'braise';
}

/**
 * Couleur d'action resolue (--action) du theme/accent courant, pour les
 * usages JS qui exigent une vraie couleur (trace maptiler, SVG inline,
 * canvas) la ou une var CSS n'est pas acceptee. Suit donc l'accent
 * (braise par defaut). Fallback = brique braise (dark) si indisponible.
 */
export function actionColor(fallback = '#BE5638'): string {
  if (typeof document === 'undefined') return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue('--action').trim();
  return v || fallback;
}

export function applyAccent(accent: Accent): void {
  document.documentElement.setAttribute('data-accent', accent);
}

export function setAccent(accent: Accent): void {
  try {
    localStorage.setItem(ACCENT_STORAGE_KEY, accent);
  } catch {
    /* ignore */
  }
  applyAccent(accent);
}
