/**
 * Préférence de thème de la carte (MapTiler), indépendante mais alignable
 * sur le thème de l'app.
 *
 *   - 'light'  : carte toujours claire (outdoor-v4).
 *   - 'dark'   : carte toujours sombre (outdoor-v4-dark).
 *   - 'system' : suit le thème résolu de l'app (donc sombre quand le mode
 *                sombre est actif). Valeur par défaut.
 *
 * Stockée en localStorage et exposée via un petit store useSyncExternalStore
 * pour que le sélecteur (profil) et les cartes restent synchronisés sans
 * provider dédié.
 */

import { useSyncExternalStore } from 'react';

export type MapThemePref = 'light' | 'dark' | 'system';

/** IDs de style MapTiler non dépréciés (évite les warnings outdoor-v2). */
export const MAP_STYLE_LIGHT = 'outdoor-v4';
export const MAP_STYLE_DARK = 'outdoor-v4-dark';

const STORAGE_KEY = 'agon-map-theme';
const listeners = new Set<() => void>();

export function getMapThemePref(): MapThemePref {
  if (typeof localStorage === 'undefined') return 'system';
  const value = localStorage.getItem(STORAGE_KEY);
  return value === 'light' || value === 'dark' || value === 'system'
    ? value
    : 'system';
}

export function setMapThemePref(pref: MapThemePref): void {
  if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, pref);
  listeners.forEach((listener) => listener());
}

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  // `storage` couvre la synchro inter-onglets ; les listeners internes
  // couvrent la synchro intra-onglet (sélecteur ↔ cartes).
  window.addEventListener('storage', callback);
  return () => {
    listeners.delete(callback);
    window.removeEventListener('storage', callback);
  };
}

/** Hook réactif : renvoie la préférence courante et se met à jour au changement. */
export function useMapThemePref(): MapThemePref {
  return useSyncExternalStore(subscribe, getMapThemePref, () => 'system');
}

/**
 * Résout la préférence en thème effectif ('light' | 'dark') à partir du
 * thème app résolu (next-themes). `system` → suit l'app.
 */
export function resolveMapDark(
  pref: MapThemePref,
  appResolvedTheme: string | undefined,
): boolean {
  if (pref === 'dark') return true;
  if (pref === 'light') return false;
  return appResolvedTheme === 'dark';
}
