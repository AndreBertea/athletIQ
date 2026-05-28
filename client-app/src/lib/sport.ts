/**
 * Helpers Sport — emoji / label par discipline.
 *
 * Source de vérité : `web/src/types/domain.ts` (type Sport) + onboarding
 * artboard 03 (mapping emoji visible).
 */

import type { Sport } from '@/types/domain';

const SPORT_EMOJI: Record<Sport, string> = {
  hiking: '🥾',
  running: '🏃',
  cycling: '🚴',
  trail: '🏔️',
  mtb: '🚵',
  ebike: '⚡',
};

const SPORT_LABEL_FR: Record<Sport, string> = {
  hiking: 'Randonnée',
  running: 'Course à pied',
  cycling: 'Vélo',
  trail: 'Trail',
  mtb: 'VTT',
  ebike: 'VAE',
};

export function sportEmoji(code: Sport): string {
  return SPORT_EMOJI[code];
}

export function sportLabelFr(code: Sport): string {
  return SPORT_LABEL_FR[code];
}
