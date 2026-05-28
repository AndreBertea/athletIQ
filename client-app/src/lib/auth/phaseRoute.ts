/**
 * Centralise le mapping phase utilisateur → route par défaut au login.
 * Utilisé par auth.tsx (démo sheet) et par les guards globaux d'App.tsx.
 *
 */

import type { UserPhase } from '@/types/domain';

export function phaseDefaultRoute(phase: UserPhase): string {
  switch (phase) {
    case 'onboarding':
      return '/onboarding';
    case 'calibration':
    case 'stable':
      return '/home';
  }
}
