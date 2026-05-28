/**
 * DimensionStrip — décomposition par dimension (4 lignes).
 *
 * Portage 1:1 de `screens.jsx` → `DimensionStrip` (lignes 269–298). Chaque
 * ligne expose la valeur brute (1–5), l'emoji de la dimension, le z-score
 * (si calibré), et une pastille de couleur.
 *
 * Comportement gating :
 *   - showZ=false  → mode calibration : pas de z, pas de pastille colorée.
 *     Toutes les pastilles sont neutralisées (la prop color est ignorée).
 *   - showZ=true   → mode stable : z formaté ±X.X et pastille couleur z.
 *
 * Lecture forcée (DimensionStrip TOUJOURS sous le ScoreGauge en J14+) —
 * cf. ADR 11/15 + Duignan 2020.
 */

import { useTranslation } from 'react-i18next';
import type { DimensionScore, ZColor } from '@/types/domain';
import { cn } from '@/lib/utils';

interface DimensionStripProps {
  dimensions: DimensionScore[];
  /** false en calibration (J<14) — masque z + pastille colorée. */
  showZ: boolean;
  className?: string;
}

const DOT_BG: Record<ZColor, string> = {
  green: 'bg-success',
  orange: 'bg-warning',
  red: 'bg-danger',
};

const EMOJI: Record<DimensionScore['key'], string> = {
  wellbeing: '🙂',
  sleep_quality: '🛏️',
  legs: '🦵',
  motivation: '🔥',
};

export function DimensionStrip({
  dimensions,
  showZ,
  className,
}: DimensionStripProps) {
  const { t } = useTranslation();
  return (
    <ul
      className={cn(
        'bg-card border-border-subtle overflow-hidden rounded-md border',
        className,
      )}
    >
      {dimensions.map((dim, idx) => {
        const isLast = idx === dimensions.length - 1;
        const label = capitalize(t(`home.dimensionLabels.${dim.key}`));
        return (
          <li
            key={dim.key}
            className={cn(
              'flex items-center gap-3 px-4',
              !isLast && 'border-border-subtle border-b',
            )}
            style={{ height: 56 }}
          >
            <span className="text-foreground flex-1 text-sm font-medium">
              {label}
            </span>
            <span className="font-display text-foreground text-lg font-bold tracking-tight">
              {dim.value}
              <span className="font-display text-muted-foreground text-xs font-medium">
                /5
              </span>
            </span>
            <span aria-hidden className="text-lg leading-none">
              {EMOJI[dim.key]}
            </span>
            {showZ ? (
              <>
                <span className="text-muted-foreground min-w-[46px] text-right text-[11px] font-medium">
                  z={formatZ(dim.z)}
                </span>
                <span
                  aria-hidden
                  className={cn(
                    'inline-block rounded-full',
                    DOT_BG[dim.color],
                  )}
                  style={{ width: 8, height: 8 }}
                />
              </>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function formatZ(z: number | null): string {
  if (z === null || !Number.isFinite(z)) return '—';
  // Use the visual unicode minus when negative for typographic consistency.
  const sign = z >= 0 ? '+' : '−';
  return `${sign}${Math.abs(z).toFixed(1)}`;
}

function capitalize(s: string): string {
  return s.length === 0 ? s : s.charAt(0).toUpperCase() + s.slice(1);
}
