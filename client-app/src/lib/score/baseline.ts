/**
 * Baseline helpers.
 *
 * La vue Postgres `readiness_baseline` (migration 005) expose pour chaque
 * user les moyennes et écarts-types 28 j de chaque dimension wellness, du
 * sRPE et du score composite. et §5.5.
 *
 * Ces helpers normalisent l'accès aux paires (mean, sd) par dimension
 * pour les composants score et insights, et exposent le gating J14 sous
 * forme d'un booléen `isCalibrated()`.
 */

import type {
  BaselineRow,
  DimensionKey,
  DimensionScore,
} from '@/types/domain';
import { DIMENSION_KEYS } from '@/types/domain';
import { dimColor, zScore } from './zscore';

/** Seuil minimal de jours enregistrés pour activer le score 0–100 (Saw 2017). */
export const CALIBRATION_DAYS = 14;

/** Paire mean/sd extraite d'une baseline pour une dimension. */
export interface BaselineStats {
  mean: number | null;
  sd: number | null;
}

const ZERO_STATS: BaselineStats = { mean: null, sd: null };

/**
 * `true` si la baseline contient au moins 14 saisies — gating strict côté
 * UI. Toute requête front qui décide d'afficher
 * un score 0–100 ou un z-score doit passer par cette fonction.
 */
export function isCalibrated(baseline: BaselineRow | null | undefined): boolean {
  if (!baseline) return false;
  return baseline.days_recorded >= CALIBRATION_DAYS;
}

/** Nb de jours saisis sur la fenêtre 28 j (0 si baseline absente). */
export function daysRecorded(baseline: BaselineRow | null | undefined): number {
  return baseline?.days_recorded ?? 0;
}

/** Extrait la paire (mean, sd) d'une dimension donnée. */
export function dimensionStats(
  baseline: BaselineRow | null | undefined,
  key: DimensionKey,
): BaselineStats {
  if (!baseline) return ZERO_STATS;
  switch (key) {
    case 'wellbeing':
      return { mean: baseline.wellbeing_mean_28d, sd: baseline.wellbeing_sd_28d };
    case 'sleep_quality':
      return { mean: baseline.sleep_mean_28d, sd: baseline.sleep_sd_28d };
    case 'legs':
      return { mean: baseline.legs_mean_28d, sd: baseline.legs_sd_28d };
    case 'motivation':
      return {
        mean: baseline.motivation_mean_28d,
        sd: baseline.motivation_sd_28d,
      };
  }
}

/** (mean, sd) du score composite 0–100 sur la fenêtre 28 j. */
export function scoreStats(
  baseline: BaselineRow | null | undefined,
): BaselineStats {
  if (!baseline) return ZERO_STATS;
  return { mean: baseline.score_mean_28d, sd: baseline.score_sd_28d };
}

/**
 * Construit la décomposition par dimension utilisée par DimensionStrip.
 * Si non calibré, z = null et color = 'green' par défaut (l'UI masque le z).
 */
export interface DimensionInputs {
  wellbeing: number;
  sleep_quality: number;
  legs: number;
  motivation: number;
}

export function buildDimensionScores(
  values: DimensionInputs,
  baseline: BaselineRow | null | undefined,
  calibrated: boolean,
): DimensionScore[] {
  return DIMENSION_KEYS.map((key) => {
    const value = values[key];
    if (!calibrated) {
      return {
        key,
        value,
        z: null,
        color: 'green' as const,
      };
    }
    const stats = dimensionStats(baseline, key);
    const z = zScore(value, stats.mean, stats.sd);
    return {
      key,
      value,
      z,
      color: dimColor(value, stats.mean, stats.sd),
    };
  });
}
