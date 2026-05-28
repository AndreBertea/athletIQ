/**
 * useUpdateProfile() — STUB temporaire.
 *
 * TODO(agon-backend) : le backend AGON n'expose pas encore de
 * route `PATCH /api/v1/auth/me` ni de table `profiles` séparée du `users`.
 * Tant que ce endpoint n'existe pas, ce hook reste un no-op qui :
 *   1. relit le profil courant via `useProfile()` pour avoir une donnée
 *      retournable cohérente (évite que les consommateurs casent sur
 *      `mutation.data` undefined),
 *   2. n'effectue AUCUN appel réseau ni écriture serveur,
 *   3. invalide quand même la query profile en local pour signaler aux
 *      composants qu'ils peuvent re-rendre avec leur état optimiste.
 *
 * Les écrans `/profile` et `/onboarding` peuvent ainsi continuer à
 * appeler `updateProfile.mutate({ patch: {...} })` sans crash. Les
 * préférences mutées (sport, heure de check-in, streak_visible) ne sont
 * pas persistées tant que l'endpoint backend n'est pas créé. Un warning
 * console est émis pour rendre cet état visible en dev.
 */

import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import type { Profile } from '@/types/domain';
import { PROFILE_QUERY_KEY, useProfile } from './useProfile';

// Les composants consommateurs (profile.tsx, onboarding.tsx) passent un
// `patch` typé librement (sport, notif_local_time, streak_visible, ...).
// On garde un type ouvert tant que le backend ne fige pas le contrat.
interface UpdateProfileVariables {
  patch: Record<string, unknown>;
}

export function useUpdateProfile(): UseMutationResult<
  Profile,
  Error,
  UpdateProfileVariables
> {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const userId = user?.id ?? null;
  const profileQuery = useProfile();

  return useMutation<Profile, Error, UpdateProfileVariables>({
    mutationFn: async ({ patch }) => {
      if (!userId) throw new Error('Utilisateur non connecté');
      // eslint-disable-next-line no-console
      console.warn(
        '[useUpdateProfile] No-op : endpoint backend non implémenté.',
        'Patch reçu (non persisté) :',
        patch,
      );
      // On renvoie le profil courant comme "data" pour que les composants
      // n'aient pas un `undefined` ; si la query profile n'a pas (encore)
      // de données on retombe sur un Profile vide minimal.
      const current = profileQuery.data ?? null;
      if (current) return current;
      return {
        id: userId,
        email: user?.email ?? '',
        full_name: user?.displayName ?? '',
        created_at: new Date().toISOString(),
      } as Profile;
    },
    onSuccess: (next) => {
      queryClient.setQueryData([...PROFILE_QUERY_KEY, userId], next);
    },
  });
}
