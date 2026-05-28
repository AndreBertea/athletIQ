/**
 * useReadinessScore — produit le `ScoreResult` consommé par les routes
 * Home et Check-in Done.
 *
 * Implémentation :
 *   - `GET /api/v1/checkin/score` (backend AGON) fournit la vérité
 *     consolidée : phase (`no_entries | calibration | stable`),
 *     `days_recorded`, score 0–100 et z-scores par dimension.
 *   - `useTodayEntry()` fournit les valeurs brutes du jour (nécessaires
 *     pour la décomposition par dimension et la couleur des badges).
 *   - `useBaseline()` (calcul local en JS depuis l'historique) sert au
 *     `computeScore()` local pour produire le `ScoreResult` complet —
 *     en particulier l'`insight` i18n et les `dimensions[].color`.
 *
 * Le backend reste prioritaire sur les agrégats (`score`, `daysRecorded`,
 * `calibrated`) ; on retombe sur le calcul local pour les champs qu'il
 * n'expose pas (dimensions détaillées, insight descripteur).
 *
 * Le calcul est mémoïsé sur les références (entry, baseline, score
 * backend) — TanStack Query garantit que ces références sont stables
 * entre re-renders tant que les données n'ont pas changé.
 */

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { computeScore } from '@/lib/score/compute';
import { useBaseline } from './useBaseline';
import { useTodayEntry } from './useTodayEntry';
import type { ScoreResult } from '@/types/domain';

export const READINESS_SCORE_QUERY_KEY = ['readiness', 'score'] as const;

/** Forme brute renvoyée par le backend (`GET /api/v1/checkin/score`). */
interface BackendReadinessScore {
  phase: 'no_entries' | 'calibration' | 'stable';
  days_recorded: number;
  days_required: number;
  score_0_100?: number | null;
  z_wellbeing?: number | null;
  z_sleep?: number | null;
  z_legs?: number | null;
  z_motivation?: number | null;
  today?: unknown;
  insight?: string | null;
}

export interface UseReadinessScoreResult {
  /** Résultat consolidé prêt pour l'UI. */
  scoreResult: ScoreResult;
  /** true tant qu'au moins l'une des deux requêtes est en chargement. */
  isLoading: boolean;
  /** true si l'utilisateur n'a pas encore saisi sa journée. */
  hasTodayEntry: boolean;
}

export function useReadinessScore(): UseReadinessScoreResult {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const todayQuery = useTodayEntry();
  const baselineQuery = useBaseline();

  const scoreQuery = useQuery<BackendReadinessScore | null>({
    queryKey: [...READINESS_SCORE_QUERY_KEY, userId],
    enabled: userId !== null,
    staleTime: 30_000,
    queryFn: async () => {
      const { data } = await api.get<BackendReadinessScore>('/checkin/score');
      return data ?? null;
    },
  });

  const entry = todayQuery.data ?? null;
  const baseline = baselineQuery.data ?? null;
  const backendScore = scoreQuery.data ?? null;

  const scoreResult = useMemo<ScoreResult>(() => {
    // Calcul local complet (dimensions, couleurs, insight i18n).
    const local = computeScore(entry, baseline);

    // Override des agrégats avec les valeurs du backend si dispo.
    if (!backendScore) return local;
    const calibratedBackend = backendScore.phase === 'stable';
    return {
      ...local,
      calibrated: calibratedBackend,
      daysRecorded: backendScore.days_recorded,
      score:
        backendScore.score_0_100 !== undefined &&
        backendScore.score_0_100 !== null
          ? Math.round(backendScore.score_0_100)
          : local.score,
    };
  }, [entry, baseline, backendScore]);

  return {
    scoreResult,
    isLoading:
      todayQuery.isLoading || baselineQuery.isLoading || scoreQuery.isLoading,
    hasTodayEntry: entry !== null,
  };
}
