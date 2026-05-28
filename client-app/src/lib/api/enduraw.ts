/**
 * Placeholders pour les futurs endpoints Enduraw API (V1.1).
 *
 * surface d'API consommée par les hooks/composants. En V1, elles renvoient
 * des données mockées ou throw `'Disponible prochainement'`. En V1.1, on
 * remplace l'implémentation par des fetch vers /api/v2/* sans toucher
 * aux composants.
 */

export interface EnduRawProfile {
  id: string;
  displayName: string;
  primarySport: string;
  coachAssigned: boolean;
}

export interface CoachFeedItem {
  seenAt: string;     // ISO timestamp
  message: string | null;
}

export interface CoachNoteInput {
  body: string;
  visibleToAthlete: boolean;
}

export interface TrainingSession {
  date: string;
  type: 'run' | 'bike' | 'rest' | 'strength' | 'other';
  durationMin: number | null;
  description: string;
}

const NOT_IMPLEMENTED = 'Disponible prochainement';

// TODO: replace with real Enduraw API call when /api/v2/auth/oauth is wired
export async function oauthLogin(_code: string): Promise<never> {
  throw new Error(NOT_IMPLEMENTED);
}

// TODO: replace with real Enduraw API call when /api/v2/me is wired
export async function fetchEnduRawProfile(): Promise<EnduRawProfile | null> {
  return null;
}

// TODO: replace with real Enduraw API call when /api/v2/coach/feed is wired
export async function fetchCoachFeed(): Promise<CoachFeedItem[]> {
  // Mock V1 : un seul item « ton coach a vu ta saisie il y a 2 h ».
  return [
    {
      seenAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
      message: null,
    },
  ];
}

// TODO: replace with real Enduraw API call when /api/v2/coach/note is wired
export async function postCoachNote(_input: CoachNoteInput): Promise<never> {
  throw new Error(NOT_IMPLEMENTED);
}

// TODO: replace with real Enduraw API call when /api/v2/training/today is wired
export async function fetchTodayTraining(): Promise<TrainingSession | null> {
  return null;
}

// TODO: replace with real Enduraw API call when /api/v2/readiness/sync is wired
export async function syncReadinessToEnduRaw(_userId: string): Promise<never> {
  throw new Error(NOT_IMPLEMENTED);
}
