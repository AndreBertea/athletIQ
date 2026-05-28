/**
 * useStreak() — calcule le streak avec freeze auto à partir de l'historique.
 *
 *
 * Combine `useHistory()` et `computeStreak()`. Retourne :
 *   - `streak.length` : nb de jours du streak (saisis + freezes).
 *   - `streak.frozenDays` : freezes consommés.
 *   - `streak.freezeAvailable` : true si un freeze est encore dispo
 *     dans la fenêtre 7 j courante.
 *   - `isLoading` / `isError` : passés depuis useHistory.
 */

import { useMemo } from 'react';
import { useHistory } from './useHistory';
import {
  computeStreak,
  type StreakResult,
} from '@/lib/streak/streak';

interface UseStreakResult {
  streak: StreakResult;
  isLoading: boolean;
  isError: boolean;
}

/**
 * Lookback : on prend par défaut 60 jours pour avoir de la marge sur
 * un éventuel streak long. Le hook délègue à useHistory(60).
 */
export function useStreak(lookbackDays = 60): UseStreakResult {
  const history = useHistory(lookbackDays);

  const streak = useMemo<StreakResult>(() => {
    const entries = history.data;
    if (!entries || entries.length === 0) {
      return { length: 0, frozenDays: 0, freezeAvailable: true };
    }
    const dates = entries.map((e) => e.entry_date);
    return computeStreak(dates);
  }, [history.data]);

  return {
    streak,
    isLoading: history.isLoading,
    isError: history.isError,
  };
}
