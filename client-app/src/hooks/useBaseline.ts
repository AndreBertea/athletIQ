/**
 * useBaseline — calcule en JS la baseline 28 j (moyennes + écarts-types)
 * depuis l'historique exposé par l'API AGON.
 *
 * Le backend AGON n'a plus de vue SQL `readiness_baseline` ; on
 * reconstitue la même structure `BaselineRow` côté client à partir des
 * dernières entries (`useHistory(28)`). Cela préserve la compatibilité
 * binaire avec `lib/score/baseline.ts` et `lib/score/compute.ts` sans
 * toucher au code de scoring existant.
 *
 * Retourne `null` tant que l'historique n'a pas chargé ou s'il est vide
 * (utilisateur tout neuf). Les hooks consommateurs traitent ce null comme
 * "non calibré" via `isCalibrated()` dans `lib/score/baseline.ts`.
 */

import { useMemo } from 'react';
import type { UseQueryResult } from '@tanstack/react-query';
import { useHistory } from './useHistory';
import type { BaselineRow, ReadinessEntry } from '@/types/domain';

/** Fenêtre glissante de référence (Saw 2017, fenêtre 28 j). */
const BASELINE_WINDOW_DAYS = 28;

/** Moyenne arithmétique d'un échantillon de nombres finis. */
function mean(values: number[]): number | null {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return null;
  const sum = finite.reduce((acc, v) => acc + v, 0);
  return sum / finite.length;
}

/** Écart-type non biaisé (n-1). Retourne null si n < 2. */
function stdDev(values: number[]): number | null {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length < 2) return null;
  const m = finite.reduce((a, v) => a + v, 0) / finite.length;
  const variance =
    finite.reduce((acc, v) => acc + (v - m) ** 2, 0) / (finite.length - 1);
  return Math.sqrt(variance);
}

/** Score composite brut 0–100 d'une entry (mean wellness × 20). */
function compositeScore(entry: ReadinessEntry): number {
  return (
    ((entry.wellbeing + entry.sleep_quality + entry.legs + entry.motivation) /
      4) *
    20
  );
}

function buildBaseline(entries: ReadinessEntry[]): BaselineRow | null {
  if (!entries || entries.length === 0) return null;

  // L'historique est trié desc côté backend ; on prend les 28 plus récents.
  const window = entries.slice(0, BASELINE_WINDOW_DAYS);
  const wellbeing = window.map((e) => e.wellbeing);
  const sleep = window.map((e) => e.sleep_quality);
  const legs = window.map((e) => e.legs);
  const motivation = window.map((e) => e.motivation);
  const composite = window.map(compositeScore);

  return {
    days_recorded: window.length,
    wellbeing_mean_28d: mean(wellbeing),
    wellbeing_sd_28d: stdDev(wellbeing),
    sleep_mean_28d: mean(sleep),
    sleep_sd_28d: stdDev(sleep),
    legs_mean_28d: mean(legs),
    legs_sd_28d: stdDev(legs),
    motivation_mean_28d: mean(motivation),
    motivation_sd_28d: stdDev(motivation),
    score_mean_28d: mean(composite),
    score_sd_28d: stdDev(composite),
  } as BaselineRow;
}

/**
 * Wrapper read-only qui exposera la même forme `UseQueryResult` qu'avant.
 * On s'appuie sur `useHistory()` (déjà mis en cache react-query) pour
 * éviter une requête réseau supplémentaire et profiter automatiquement
 * de l'invalidation déclenchée par `useSubmitEntry`.
 */
export function useBaseline(): UseQueryResult<BaselineRow | null> {
  const history = useHistory(BASELINE_WINDOW_DAYS);

  const baseline = useMemo<BaselineRow | null>(() => {
    if (!history.data) return null;
    return buildBaseline(history.data);
  }, [history.data]);

  // On reconstruit un objet "shape UseQueryResult" en proxy de la query
  // sous-jacente, en remplaçant `data` par la baseline calculée. Cela
  // évite d'écrire un useQuery dédié juste pour ré-emballer les flags.
  return {
    ...history,
    data: baseline,
  } as UseQueryResult<BaselineRow | null>;
}
