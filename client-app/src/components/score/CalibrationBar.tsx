/**
 * CalibrationBar — barre de progression J{n}/14.
 *
 * Affiché à la place du ScoreGauge tant que `days_recorded < 14` (Saw
 * 2017, gating strict).
 *
 * Sobre, motivante et NON culpabilisante : pas de mascotte, pas de
 * compteur de streak, pas de "ne casse pas ta série". Le chiffre
 * J{n}/14 est l'élément hero, le reste reste descriptif.
 */

import { useTranslation } from 'react-i18next';
import { CALIBRATION_DAYS } from '@/lib/score/baseline';
import { cn } from '@/lib/utils';

interface CalibrationBarProps {
  /** Nombre de jours saisis (clampé sur [0, CALIBRATION_DAYS]). */
  daysRecorded: number;
  className?: string;
}

export function CalibrationBar({
  daysRecorded,
  className,
}: CalibrationBarProps) {
  const { t } = useTranslation();
  const day = Math.max(0, Math.min(CALIBRATION_DAYS, daysRecorded));
  const remaining = CALIBRATION_DAYS - day;
  const pct = (day / CALIBRATION_DAYS) * 100;

  const remainingText =
    remaining > 0
      ? remaining > 1
        ? t('home.calibration.remainingPlural', { count: remaining })
        : t('home.calibration.remainingOne', { count: remaining })
      : t('home.calibration.complete');

  return (
    <div
      className={cn(
        'bg-card border-border-subtle rounded-md border p-5',
        className,
      )}
    >
      <div className="mb-3.5 flex items-start justify-between">
        <span className="text-eyebrow">
          {t('home.calibration.eyebrow')}
        </span>
        <span
          className="font-display text-foreground font-bold leading-none tracking-tight"
          style={{ fontSize: '24px' }}
        >
          J{day}
          <span className="text-muted-foreground">
            /{CALIBRATION_DAYS}
          </span>
        </span>
      </div>

      <div
        className="bg-surface-2 overflow-hidden rounded-full"
        style={{ height: 8 }}
        role="progressbar"
        aria-valuenow={day}
        aria-valuemin={0}
        aria-valuemax={CALIBRATION_DAYS}
        aria-label={t('home.calibration.barAriaLabel')}
      >
        <div
          className="bg-brand-primary h-full rounded-full transition-[width] duration-slow ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>

      <p className="text-muted-foreground mt-3 text-[13px] leading-relaxed">
        {remainingText}
      </p>
    </div>
  );
}
