/**
 * Calcul de streak avec freeze auto (1 jour/semaine).
 *
 * Streak SOBRE, freeze auto 1 j/sem.
 *
 * Règle V1 :
 *   - On part du jour le plus récent (today) et on remonte jour par jour.
 *   - Sur toute fenêtre glissante de 7 jours qui inclut le jour courant,
 *     si nb_jours_sans_saisie ≤ 1, le streak continue.
 *   - Le streak s'arrête au premier jour où la fenêtre 7 j sortante
 *     contient ≥ 2 trous.
 *   - Le streak n'inclut pas les jours antérieurs à la première saisie
 *     connue (un nouvel utilisateur ne consomme pas son freeze pour
 *     du néant).
 *
 * Le résultat distingue :
 *   - `length` : nombre total de jours du streak (saisis + freezes inclus).
 *   - `frozenDays` : nombre de freezes consommés (jours sans saisie tolérés).
 *   - `freezeAvailable` : true si la fenêtre 7 j courante contient
 *     0 freeze consommé — affichage UI sobre type « freeze auto ».
 */

export interface StreakResult {
  length: number;
  frozenDays: number;
  freezeAvailable: boolean;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function toDayKey(d: Date): string {
  // YYYY-MM-DD UTC — match Supabase DATE column.
  return d.toISOString().slice(0, 10);
}

function previousDay(d: Date): Date {
  return new Date(d.getTime() - DAY_MS);
}

function parseEntryDate(s: string): Date {
  // s = 'YYYY-MM-DD' — interprété UTC pour rester aligné avec Postgres DATE.
  return new Date(`${s}T00:00:00.000Z`);
}

/**
 * Calcule le streak à partir d'un set de dates de saisie et d'une date
 * de référence (par défaut today). `entryDates` peut être en n'importe
 * quel ordre — la fonction ne mutate pas l'input.
 */
export function computeStreak(
  entryDates: readonly string[],
  todayIso: string = toDayKey(new Date()),
): StreakResult {
  const entrySet = new Set(entryDates);
  if (entrySet.size === 0) {
    return { length: 0, frozenDays: 0, freezeAvailable: true };
  }
  const today = parseEntryDate(todayIso);
  const todayKey = toDayKey(today);
  const yesterdayKey = toDayKey(previousDay(today));

  // S'il n'y a pas de saisie aujourd'hui ni hier, pas de streak.
  if (!entrySet.has(todayKey) && !entrySet.has(yesterdayKey)) {
    return { length: 0, frozenDays: 0, freezeAvailable: true };
  }

  // Borne basse : la plus ancienne date saisie. On ne descend pas sous
  // cette date, sinon on consomme un freeze pour du néant.
  const earliestEntryKey = [...entrySet].sort()[0];
  if (!earliestEntryKey) {
    return { length: 0, frozenDays: 0, freezeAvailable: true };
  }
  const earliestDate = parseEntryDate(earliestEntryKey);

  let cursor = today;
  let length = 0;
  let frozenDays = 0;
  // window[i] = true si gap. Sliding window des 7 derniers jours en cours
  // d'examen (du curseur en remontant). Un freeze (1 gap) est OK ; ≥ 2
  // gaps stoppent l'inclusion du jour courant.
  const window: boolean[] = [];

  while (cursor.getTime() >= earliestDate.getTime()) {
    const key = toDayKey(cursor);
    const isGap = !entrySet.has(key);

    if (isGap) {
      // Combien de gaps si on inclut ce jour dans la fenêtre 7 j ?
      const futureWindow = [true, ...window.slice(0, 6)];
      const gapsInWindow = futureWindow.filter(Boolean).length;
      if (gapsInWindow > 1) {
        // Le freeze est saturé — on stoppe AVANT d'inclure ce jour.
        break;
      }
      frozenDays += 1;
    }

    length += 1;
    window.unshift(isGap);
    if (window.length > 7) window.pop();

    cursor = previousDay(cursor);
    // Garde-fou : 365 jours max.
    if (length > 365) break;
  }

  // freezeAvailable : on regarde les 7 jours calendaires les plus récents
  // dans la limite du streak (qui borne à `earliestEntryKey`). Pour un
  // utilisateur récent (ex. Thomas 6 j), les jours antérieurs à sa
  // première saisie ne comptent PAS comme gap.
  let gapsInLast7Calendar = 0;
  for (let i = 0; i < 7; i++) {
    const dayDate = new Date(today.getTime() - i * DAY_MS);
    if (dayDate.getTime() < earliestDate.getTime()) break;
    const dayKey = toDayKey(dayDate);
    if (!entrySet.has(dayKey)) gapsInLast7Calendar += 1;
  }
  const freezeAvailable = gapsInLast7Calendar === 0;

  return { length, frozenDays, freezeAvailable };
}
