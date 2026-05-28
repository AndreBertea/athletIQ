/**
 * Types métier exposés aux composants.
 *
 * Auparavant ces types dérivaient d'un placeholder Supabase
 * (`src/types/database.ts`). Cette couche a été supprimée avec la
 * bascule sur le backend AGON (FastAPI + JWT cookies). On expose
 * désormais des types alignés sur les réponses de l'API REST :
 *   - `Profile` : forme renvoyée par `GET /api/v1/auth/me` étendue côté
 *     produit. Tant que l'endpoint backend n'expose pas les champs
 *     spécifiques readiness (sport, timezone, …), le modèle reste limité
 *     aux 4 colonnes brutes — les hooks qui veulent les champs étendus
 *     devront soit étendre le backend, soit stocker en local.
 *   - `ReadinessEntry` : forme attendue côté futurs endpoints readiness
 *     (à créer côté backend). Champs minimum nécessaires pour le score
 *     côté client.
 *
 * Les enums (`Sport`, `EntrySource`, `ClientOrigin`) restent exposés car
 * ce sont des valeurs métier indépendantes du transport — ils servent à
 * typer les inputs côté formulaires et hooks même si le backend ne les
 * matérialise pas encore en colonne dédiée.
 */

export type { ContextTagCode, ContextTag } from '@/lib/checkin/contextTags';
export type { InsightDescriptor } from '@/lib/score/insights';

import type { InsightDescriptor } from '@/lib/score/insights';

// ─── Enums métier ───────────────────────────────────────────────────────

export type Sport = 'hiking' | 'running' | 'cycling' | 'trail' | 'mtb' | 'ebike';

export type EntrySource =
  | 'manual'
  | 'health_kit'
  | 'garmin'
  | 'whoop'
  | 'oura';

export type ClientOrigin = 'pwa' | 'ios_native' | 'widget_intent';

// ─── Modèles API (alignés sur backend AGON) ─────────────────────────

/**
 * Profile utilisateur — pour l'instant identique à la réponse de
 * `/api/v1/auth/me`. Quand le backend exposera les colonnes readiness
 * (sport, timezone, wakeup_time, …), elles seront ajoutées ici sans
 * casser les consommateurs déjà branchés sur `id`/`email`/`full_name`.
 */
export interface Profile {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
  primary_sport?: Sport | null;
  notif_local_time?: string | null;
  streak_visible?: boolean | null;
}

/** Subset writable de Profile — utilisé pour les PATCH côté hooks. */
export type ProfileUpdate = Partial<Pick<Profile, 'full_name'>>;

/**
 * Entrée readiness quotidienne. Forme prévue pour les futurs endpoints
 * `/api/v1/readiness/entries` côté backend ; certains champs avancés
 * (session_duration_min, source, hrv, sleep_duration_h, client_origin)
 * de l'ancien schéma Supabase ne sont volontairement plus exposés ici
 * tant qu'on ne décide pas s'ils restent côté serveur ou s'ils migrent
 * vers une table d'enrichissement séparée.
 */
export interface ReadinessEntry {
  id: string;
  entry_date: string;       // ISO yyyy-MM-dd local
  wellbeing: number;        // 1–5
  sleep_quality: number;    // 1–5
  legs: number;             // 1–5
  motivation: number;       // 1–5
  srpe_yesterday: number | null;
  session_duration_min: number | null;
  context_tags: string[];
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/** Champs writable d'une entrée — payload envoyé au backend. */
export type ReadinessEntryInsert = Pick<
  ReadinessEntry,
  | 'entry_date'
  | 'wellbeing'
  | 'sleep_quality'
  | 'legs'
  | 'motivation'
  | 'srpe_yesterday'
  | 'context_tags'
  | 'notes'
>;

// ─── Dimensions wellness ────────────────────────────────────────────────

/** 4 dimensions wellness — sRPE volontairement exclu. */
export type DimensionKey =
  | 'wellbeing'
  | 'sleep_quality'
  | 'legs'
  | 'motivation';

export const DIMENSION_KEYS: readonly DimensionKey[] = [
  'wellbeing',
  'sleep_quality',
  'legs',
  'motivation',
] as const;

/**
 * @deprecated Les libellés des dimensions sont désormais résolus via i18n
 * (clés `home.dimensionLabels.<key>`). Ce record reste exporté pour
 * compatibilité — éviter en code neuf, préférer `t('home.dimensionLabels.X')`.
 */
export const DIMENSION_LABELS_FR: Record<DimensionKey, string> = {
  wellbeing: 'bien-être',
  sleep_quality: 'sommeil',
  legs: 'jambes',
  motivation: 'motivation',
};

export type ZColor = 'green' | 'orange' | 'red';

export interface DimensionScore {
  key: DimensionKey;
  value: number;        // valeur saisie 1–5
  z: number | null;     // null tant que la baseline n'a pas de SD
  color: ZColor;        // green par défaut si non calibré
}

/**
 * Résultat consolidé du calcul score.
 * `calibrated` est false tant que `days_recorded < 14` — dans ce cas
 * `score` et `delta` valent null et l'UI affiche la barre de calibration.
 *
 * `insight` est un descripteur i18n (`{ key, vars, dimKeys }`). Le
 * composant qui rend appelle `t(key, ...)` après avoir résolu les
 * libellés des dimensions citées via i18n. `null` si pas d'entry du
 * jour — l'UI gère ce cas en n'affichant pas la carte.
 */
export interface ScoreResult {
  calibrated: boolean;
  daysRecorded: number;
  score: number | null;       // 0–100, null si non calibré
  delta: number | null;       // delta vs baseline, null si non calibré
  zScore: number | null;      // z global, null si non calibré
  color: ZColor;              // green par défaut si non calibré
  dimensions: DimensionScore[];
  insight: InsightDescriptor | null;
}

/** Phase d'un user — détermine la route par défaut au login. */
export type UserPhase = 'onboarding' | 'calibration' | 'stable';
