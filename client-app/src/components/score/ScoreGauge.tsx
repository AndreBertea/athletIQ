/**
 * ScoreGauge — jauge circulaire 0–100 pour l'écran 07-B.
 *
 * Portage 1:1 de `screens.jsx` → `ScoreGauge` (lignes 224–244). SVG arc,
 * couleur déterminée par le z-score global (vert/orange/rouge), chiffre
 * en font-display centré.
 *
 * S'utilise UNIQUEMENT quand la baseline est calibrée (J≥14). Pour J<14,
 * monter <CalibrationBar /> à la place — pas de score 0–100 affiché en
 * calibration.
 */

import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import type { ZColor } from '@/types/domain';
import { cn } from '@/lib/utils';

interface ScoreGaugeProps {
  /** Score 0–100, déjà arrondi côté logique. */
  score: number;
  /** Couleur de l'arc, fonction du z-score global (cf. zscore.ts). */
  color: ZColor;
  /** Libellé optionnel sous le score (ex. "Aujourd'hui"). */
  label?: string;
  className?: string;
}

const COLOR_VAR: Record<ZColor, string> = {
  green: 'var(--success)',
  orange: 'var(--warning)',
  red: 'var(--danger)',
};

const RADIUS = 92;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const SIZE = 200;

export function ScoreGauge({
  score,
  color,
  label,
  className,
}: ScoreGaugeProps) {
  const { t } = useTranslation();
  // Clamp & sanitize.
  const safeScore = Math.max(0, Math.min(100, Math.round(score)));
  const offset = CIRCUMFERENCE * (1 - safeScore / 100);
  const stroke = COLOR_VAR[color];
  const labelId = useId();

  return (
    <div
      className={cn('relative', className)}
      style={{ width: SIZE, height: SIZE }}
      role="img"
      aria-labelledby={labelId}
    >
      <span id={labelId} className="sr-only">
        {t('home.stable.scoreAriaLabel', { score: safeScore })}
        {label ? `, ${label}` : ''}
      </span>
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        style={{ transform: 'rotate(-90deg)' }}
      >
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth="8"
        />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={stroke}
          strokeWidth="8"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset var(--duration-slow, 400ms) var(--ease-out, ease-out)' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-display text-foreground font-extrabold leading-none tracking-tight"
          style={{ fontSize: '64px' }}
        >
          {safeScore}
        </span>
        <span className="text-muted-foreground mt-1 text-[11px] font-medium uppercase tracking-widest">
          / 100
        </span>
      </div>
    </div>
  );
}
