/**
 * WeeklySummary — footer de l'écran historique.
 *
 * Affiche la moyenne wellness des 7 derniers jours et le delta vs la
 * semaine précédente (J-7 → J-13). Texte sobre, en miroir des templates
 * d'insight — pas d'évaluation ni de jugement.
 *
 * Si la fenêtre considérée n'a pas assez de data (≥ 3 saisies par
 * semaine pour être sérieux), on rend une carte « Pas assez de données »
 * sans bavardage.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ReadinessEntry } from '@/types/domain';
import { cn } from '@/lib/utils';

interface WeeklySummaryProps {
  /** Entries du plus récent au plus ancien (sortie de useHistory). */
  entries: readonly ReadinessEntry[];
  /** Date du jour ISO (par défaut aujourd'hui). */
  todayIso?: string;
  className?: string;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function shiftDays(iso: string, deltaDays: number): string {
  const t = new Date(`${iso}T00:00:00.000Z`).getTime() + deltaDays * DAY_MS;
  return new Date(t).toISOString().slice(0, 10);
}

function rawAverage(e: ReadinessEntry): number {
  return (e.wellbeing + e.sleep_quality + e.legs + e.motivation) / 4;
}

interface WindowStats {
  count: number;
  avg: number | null;
}

function statsForWindow(
  entries: readonly ReadinessEntry[],
  fromIso: string,
  toIso: string,
): WindowStats {
  // [fromIso, toIso] inclusive
  const inWindow = entries.filter(
    (e) => e.entry_date >= fromIso && e.entry_date <= toIso,
  );
  if (inWindow.length === 0) return { count: 0, avg: null };
  const sum = inWindow.reduce((acc, e) => acc + rawAverage(e), 0);
  return { count: inWindow.length, avg: sum / inWindow.length };
}

export function WeeklySummary({
  entries,
  todayIso,
  className,
}: WeeklySummaryProps) {
  const { t } = useTranslation();
  const today = todayIso ?? isoToday();

  const { current, previous, delta, deltaPositive } = useMemo(() => {
    const cur = statsForWindow(entries, shiftDays(today, -6), today);
    const prev = statsForWindow(entries, shiftDays(today, -13), shiftDays(today, -7));
    if (cur.avg === null || prev.avg === null) {
      return {
        current: cur,
        previous: prev,
        delta: null,
        deltaPositive: false,
      };
    }
    const d = cur.avg - prev.avg;
    return {
      current: cur,
      previous: prev,
      delta: d,
      deltaPositive: d >= 0,
    };
  }, [entries, today]);

  const enoughData = current.count >= 3;

  return (
    <article
      className={cn('glass rounded-lg p-4', className)}
      aria-label={t('history.weekly.ariaLabel')}
    >
      <p className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
        {t('history.weekly.eyebrow')}
      </p>
      {!enoughData ? (
        <p className="text-muted-foreground mt-3 text-sm">
          {t('history.weekly.notEnough')}
        </p>
      ) : (
        <div className="mt-3 flex items-baseline gap-3">
          <p className="font-display text-foreground text-3xl font-bold tracking-tight">
            {current.avg!.toFixed(1)}
            <span className="text-muted-foreground ml-1 text-base font-medium">
              /5
            </span>
          </p>
          {delta !== null ? (
            <p
              className={cn(
                'text-xs font-medium',
                deltaPositive ? 'text-success' : 'text-warning',
              )}
            >
              {t('history.weekly.deltaWeek', {
                delta: `${deltaPositive ? '+' : ''}${delta.toFixed(1)}`,
              })}
            </p>
          ) : (
            <p className="text-muted-foreground text-xs">
              {t('history.weekly.deltaUnavailable')}
            </p>
          )}
        </div>
      )}
      <p className="text-muted-foreground mt-3 text-xs">
        {t('history.weekly.summary', {
          current: current.count,
          previous: previous.count,
        })}
      </p>
    </article>
  );
}

export default WeeklySummary;
