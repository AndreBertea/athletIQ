/**
 * useHistory(days?) — récupère les entries d'historique via l'API AGON
 * (`GET /api/v1/checkin/history?days=N`). Par défaut 30 jours.
 *
 * Le backend renvoie les entries du plus récent au plus ancien — l'API et
 * le contrat exposé au front sont strictement identiques à l'ancienne
 * source Supabase pour ne pas casser les composants (Heatmap, Streak,
 * WeeklySummary).
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import type { ReadinessEntry } from '@/types/domain';

export const HISTORY_QUERY_KEY = ['readiness_entries', 'history'] as const;

async function fetchHistory(days: number): Promise<ReadinessEntry[]> {
  const { data } = await api.get<ReadinessEntry[]>('/checkin/history', {
    params: { days },
  });
  return data ?? [];
}

export function useHistory(days = 30): UseQueryResult<ReadinessEntry[]> {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<ReadinessEntry[]>({
    queryKey: [...HISTORY_QUERY_KEY, userId, days],
    queryFn: () => {
      if (!userId) return Promise.resolve([]);
      return fetchHistory(days);
    },
    enabled: userId !== null,
    staleTime: 30_000,
  });
}
