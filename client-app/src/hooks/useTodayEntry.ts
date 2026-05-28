/**
 * useTodayEntry — récupère l'entrée du jour pour l'utilisateur courant via
 * l'API AGON (`GET /api/v1/checkin/today`).
 *
 * - Retourne `null` si pas d'entrée saisie aujourd'hui (le backend renvoie
 *   explicitement `null` dans ce cas, ce n'est pas une erreur).
 * - Le client `api` (lib/api) gère automatiquement le bearer JWT depuis le
 *   contexte d'auth.
 * - La query est désactivée tant qu'aucun utilisateur n'est connecté ; on
 *   évite ainsi un appel 401 inutile au démarrage avant que `AuthContext`
 *   ait rehydraté la session.
 *
 * Pré-requis runtime : un `<QueryClientProvider>` doit englober l'app
 * (mis en place par le shell).
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import type { ReadinessEntry } from '@/types/domain';

/** Renvoie YYYY-MM-DD dans la TZ locale (sans UTC drift). */
export function todayLocalDate(now: Date = new Date()): string {
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export const TODAY_ENTRY_QUERY_KEY = 'todayEntry' as const;

export function useTodayEntry(): UseQueryResult<ReadinessEntry | null, Error> {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const today = todayLocalDate();

  return useQuery<ReadinessEntry | null, Error>({
    queryKey: [TODAY_ENTRY_QUERY_KEY, userId, today],
    enabled: userId !== null,
    staleTime: 30_000,
    queryFn: async () => {
      // Le backend renvoie soit l'objet DailyCheckinRead, soit `null`
      // (saisie absente pour la date courante) ; les deux sont valides.
      const { data } = await api.get<ReadinessEntry | null>('/checkin/today');
      return data ?? null;
    },
  });
}

export default useTodayEntry;
