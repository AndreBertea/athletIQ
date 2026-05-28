/**
 * useProfile() — récupère le profil minimal de l'utilisateur courant via
 * l'API AGON (`GET /api/v1/auth/me`).
 *
 * Le backend AGON n'a pas (encore) de table `profiles` séparée : la
 * route `/auth/me` retourne le User serialisé, qui sert de profil minimal
 * `{ id, email, full_name, created_at }`. Les préférences UX (sport,
 * notifications, streak_visible, etc.) sont actuellement stockées
 * localement / dérivées — un endpoint dédié reste à modéliser côté backend
 * (cf. `useUpdateProfile`).
 *
 * En l'absence d'utilisateur connecté, le hook reste en idle (`enabled: false`).
 */

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/lib/api';
import type { Profile } from '@/types/domain';

export const PROFILE_QUERY_KEY = ['profile'] as const;

async function fetchProfile(): Promise<Profile | null> {
  const { data } = await api.get<Profile>('/auth/me');
  return data ?? null;
}

export function useProfile(): UseQueryResult<Profile | null> {
  const { user } = useAuth();
  const userId = user?.id ?? null;

  return useQuery<Profile | null>({
    queryKey: [...PROFILE_QUERY_KEY, userId],
    queryFn: () => {
      if (!userId) return Promise.resolve(null);
      return fetchProfile();
    },
    enabled: userId !== null,
    staleTime: 60_000,
  });
}
