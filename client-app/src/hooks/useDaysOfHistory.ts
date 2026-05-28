/**
 * useDaysOfHistory — wrapper simple qui expose `days_recorded` issu de
 * `useBaseline()`. Utilisé par les composants qui veulent juste savoir où
 * l'utilisateur en est dans la calibration sans tirer toute la baseline.
 *
 * Retourne 0 tant que la baseline n'a pas chargé.
 */

import { useBaseline } from './useBaseline';

export function useDaysOfHistory(): number {
  const { data } = useBaseline();
  return data?.days_recorded ?? 0;
}
