/**
 * useSubmitEntry — upsert de l'entrée du jour via l'API AGON
 * (`POST /api/v1/checkin`). Le backend upsert sur (user_id, entry_date).
 *
 * - Mutation TanStack Query avec optimistic update sur la query
 *   `['todayEntry', userId, today]` pour un retour instantané UX.
 * - Invalide à la fin les queries `[TODAY_ENTRY_QUERY_KEY]`,
 *   `[PROFILE_QUERY_KEY]`, l'historique et le score readiness pour
 *   forcer le rafraîchissement du dashboard.
 * - Le `entry_date` est imposé en TZ user (today local) — le parent
 *   passe le payload sans avoir à se préoccuper de la date.
 *
 * Pré-requis runtime : `<QueryClientProvider>` posé en amont.
 */

import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import type { ContextTagCode, ReadinessEntry } from '@/types/domain';
import {
  TODAY_ENTRY_QUERY_KEY,
  todayLocalDate,
} from '@/hooks/useTodayEntry';
import { PROFILE_QUERY_KEY } from '@/hooks/useProfile';
import { HISTORY_QUERY_KEY } from '@/hooks/useHistory';
import { READINESS_SCORE_QUERY_KEY } from '@/hooks/useReadinessScore';

/** Champs collectés par l'écran /checkin (côté UI, avant marshalling API). */
export interface SubmitEntryPayload {
  wellbeing: number;
  sleepQuality: number;
  legs: number;
  motivation: number;
  /** sRPE de la séance d'hier — null si pas de séance veille. */
  srpeYesterday: number | null;
  /** Durée de la séance veille en minutes — null si non renseigné. */
  sessionDurationMin: number | null;
  /** Tags contextuels Q6, validés par CONTEXT_TAGS. */
  contextTags: readonly ContextTagCode[];
  /** Notes libres (V1.5 — laissé null V1). */
  notes?: string | null;
}

/** Forme exacte attendue par `POST /api/v1/checkin`. */
interface CheckinRequestBody {
  wellbeing: number;
  sleep_quality: number;
  legs: number;
  motivation: number;
  srpe_yesterday: number | null;
  session_duration_min: number | null;
  context_tags: string[];
  notes: string | null;
  entry_date: string;
}

interface SubmitEntryContext {
  previous: ReadinessEntry | null | undefined;
  optimisticKey: readonly unknown[];
}

export type SubmitEntryMutation = UseMutationResult<
  ReadinessEntry,
  Error,
  SubmitEntryPayload,
  SubmitEntryContext
>;

function buildRequestBody(payload: SubmitEntryPayload): CheckinRequestBody {
  return {
    wellbeing: payload.wellbeing,
    sleep_quality: payload.sleepQuality,
    legs: payload.legs,
    motivation: payload.motivation,
    srpe_yesterday: payload.srpeYesterday,
    session_duration_min: payload.sessionDurationMin,
    context_tags: [...payload.contextTags],
    notes: payload.notes ?? null,
    entry_date: todayLocalDate(),
  };
}

/**
 * Construit une entry "optimiste" qui ressemble à la réponse backend pour
 * mettre à jour le cache sans attendre l'aller-retour réseau. On essaie
 * de coller au shape `DailyCheckinRead` (snake_case + `id` éventuellement
 * sentinel jusqu'au retour du serveur).
 */
function buildOptimisticEntry(
  payload: SubmitEntryPayload,
  previous: ReadinessEntry | null | undefined,
): ReadinessEntry {
  const nowIso = new Date().toISOString();
  const today = todayLocalDate();
  return {
    ...(previous ?? {}),
    id: previous?.id ?? `optimistic-${today}`,
    entry_date: today,
    wellbeing: payload.wellbeing,
    sleep_quality: payload.sleepQuality,
    legs: payload.legs,
    motivation: payload.motivation,
    srpe_yesterday: payload.srpeYesterday,
    session_duration_min: payload.sessionDurationMin,
    context_tags: [...payload.contextTags],
    notes: payload.notes ?? previous?.notes ?? null,
    created_at: previous?.created_at ?? nowIso,
    updated_at: nowIso,
  } as ReadinessEntry;
}

export function useSubmitEntry(): SubmitEntryMutation {
  const qc = useQueryClient();
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const today = todayLocalDate();
  const optimisticKey = [TODAY_ENTRY_QUERY_KEY, userId, today] as const;

  return useMutation<
    ReadinessEntry,
    Error,
    SubmitEntryPayload,
    SubmitEntryContext
  >({
    mutationFn: async (payload) => {
      if (!userId) throw new Error("Pas d'utilisateur connecté.");
      const body = buildRequestBody(payload);
      const { data } = await api.post<ReadinessEntry>('/checkin', body);
      if (!data) throw new Error("Aucune entrée renvoyée par l'API.");
      return data;
    },
    onMutate: async (payload) => {
      if (!userId) return { previous: null, optimisticKey };
      await qc.cancelQueries({ queryKey: optimisticKey });
      const previous = qc.getQueryData<ReadinessEntry | null>(optimisticKey);
      qc.setQueryData<ReadinessEntry | null>(
        optimisticKey,
        buildOptimisticEntry(payload, previous),
      );
      return { previous: previous ?? null, optimisticKey };
    },
    onError: (_err, _payload, context) => {
      if (!context) return;
      qc.setQueryData(context.optimisticKey, context.previous ?? null);
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: optimisticKey });
      void qc.invalidateQueries({ queryKey: [...PROFILE_QUERY_KEY, userId] });
      void qc.invalidateQueries({ queryKey: [...HISTORY_QUERY_KEY, userId] });
      void qc.invalidateQueries({
        queryKey: [...READINESS_SCORE_QUERY_KEY, userId],
      });
    },
  });
}

export default useSubmitEntry;
