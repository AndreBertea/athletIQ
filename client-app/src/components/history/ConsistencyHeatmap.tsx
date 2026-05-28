/**
 * ConsistencyHeatmap — HERO de l'écran historique.
 *
 * Source visuelle : `docs/result/claude-design/project/screens.jsx`
 * (composant `ConsistencyHeatmap`, l. 322). Grille 30 carrés, 10 colonnes,
 * 3 lignes — ordre chronologique gauche → droite, ligne du haut = J-29.
 *
 * Couleur :
 *   - J14+ avec score : palette success / warning / danger basée sur
 *     `score.color` (ou fallback sur la moyenne wellness brute).
 *   - J<14 : palette dégradée sur la moyenne brute (1–5) → pas de
 *     classification dramatique, on respire.
 *   - Pas de saisie : carré gris (surface-2), bordure subtile.
 *
 * Tooltip natif (title=…) : date + score / moyenne / "pas de saisie".
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { daysAgo, today as localToday } from '@/seed/seed-data';
import type { ReadinessEntry, ZColor } from '@/types/domain';

interface ConsistencyHeatmapProps {
  /** Entries du plus récent au plus ancien (sortie standard de useHistory). */
  entries: readonly ReadinessEntry[];
  /**
   * Si fourni, mappe une entry vers une couleur z-score (J14+).
   * Si null pour une entry donnée, on retombe sur la moyenne brute.
   */
  scoreColor?: ((entry: ReadinessEntry) => ZColor | null) | null;
  /** Date du jour (ISO YYYY-MM-DD) — utilisée pour aligner la grille. */
  todayIso?: string;
  /** Nombre de jours à afficher (par défaut 30). */
  days?: number;
}

interface Cell {
  dateIso: string;
  entry: ReadinessEntry | null;
}

// On délègue le calcul des dates à `seed-data.ts` (`today()`/`daysAgo()`)
// qui utilisent l'heure LOCALE (`getFullYear/getMonth/getDate`). Le seed
// et le reset démo Sophie produisent leurs `entry_date` avec ces helpers,
// donc le heatmap doit utiliser la même base sinon l'entry du jour
// tombe sur une case décalée (UTC vs local) et la case "aujourd'hui"
// reste grise alors que l'entry existe en BDD.

function isoToday(): string {
  return localToday();
}

function shiftDays(_iso: string, deltaDays: number): string {
  // `deltaDays` est NÉGATIF (on regarde dans le passé) — on convertit en
  // un argument positif pour `daysAgo`.
  return daysAgo(-deltaDays);
}

function localizedDate(iso: string, locale: string): string {
  const d = new Date(`${iso}T00:00:00.000Z`);
  return d.toLocaleDateString(locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC',
  });
}

function rawAverage(entry: ReadinessEntry): number {
  return (
    (entry.wellbeing + entry.sleep_quality + entry.legs + entry.motivation) / 4
  );
}

/**
 * Couleur fallback basée sur la moyenne wellness brute (1–5).
 * Palette qui respire : pas d'agressivité visuelle.
 */
function fallbackColorClass(avg: number): string {
  if (avg >= 4) return 'bg-success/70';
  if (avg >= 3) return 'bg-warning/55';
  return 'bg-danger/45';
}

function colorClassFromZ(z: ZColor): string {
  switch (z) {
    case 'green':
      return 'bg-success/75';
    case 'orange':
      return 'bg-warning/65';
    case 'red':
      return 'bg-danger/55';
  }
}

export function ConsistencyHeatmap({
  entries,
  scoreColor = null,
  todayIso,
  days = 30,
}: ConsistencyHeatmapProps) {
  const { t, i18n } = useTranslation();
  const localeTag =
    i18n.resolvedLanguage === 'en' ? 'en-GB' : 'fr-FR';
  const today = todayIso ?? isoToday();

  const byDate = useMemo(() => {
    const map = new Map<string, ReadinessEntry>();
    for (const e of entries) map.set(e.entry_date, e);
    return map;
  }, [entries]);

  const cells = useMemo<Cell[]>(() => {
    // Ordre chronologique : du plus ancien (J-29) au plus récent (J0).
    const out: Cell[] = [];
    for (let i = days - 1; i >= 0; i--) {
      const iso = shiftDays(today, -i);
      out.push({ dateIso: iso, entry: byDate.get(iso) ?? null });
    }
    return out;
  }, [byDate, today, days]);

  return (
    <div>
      <div
        className="grid gap-1"
        style={{ gridTemplateColumns: 'repeat(10, minmax(0, 1fr))' }}
      >
        {cells.map(({ dateIso, entry }) => {
          const dateLabel = localizedDate(dateIso, localeTag);
          if (!entry) {
            const noEntryLabel = t('history.heatmap.noEntry', {
              date: dateLabel,
            });
            return (
              <div
                key={dateIso}
                className="border-border-subtle bg-surface-2 aspect-square rounded-sm border"
                title={noEntryLabel}
                aria-label={noEntryLabel}
              />
            );
          }
          const z = scoreColor?.(entry) ?? null;
          const colorClass = z
            ? colorClassFromZ(z)
            : fallbackColorClass(rawAverage(entry));
          const tooltipLabel = z
            ? t('history.heatmap.entry', { date: dateLabel })
            : t('history.heatmap.entryAvg', {
                date: dateLabel,
                avg: rawAverage(entry).toFixed(1),
              });
          return (
            <div
              key={dateIso}
              className={cn('aspect-square rounded-sm', colorClass)}
              title={tooltipLabel}
              aria-label={tooltipLabel}
            />
          );
        })}
      </div>

      <div className="text-muted-foreground mt-3 flex items-center justify-between text-xs">
        <span>{t('history.rangeLabel', { count: days })}</span>
        <Legend />
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex items-center gap-2">
      <span className="border-border-subtle bg-surface-2 h-3 w-3 rounded-sm border" />
      <span className="bg-danger/45 h-3 w-3 rounded-sm" />
      <span className="bg-warning/55 h-3 w-3 rounded-sm" />
      <span className="bg-success/70 h-3 w-3 rounded-sm" />
    </div>
  );
}

export default ConsistencyHeatmap;
