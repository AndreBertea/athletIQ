/**
 * DimensionSparkline — carte tendance pour 1 dimension wellness.
 *
 * Source visuelle : `docs/result/claude-design/project/screens.jsx`
 * (composant `TrendCard`, l. 373). Eyebrow + valeur + delta σ + sparkline
 * Recharts. Une instance par dimension dans /history.
 *
 * On utilise Recharts `<AreaChart>` pour le rendu, mais on désactive
 * tous les axes / grilles / tooltips — on veut juste la ligne + l'aire
 * sous la courbe (style sparkline pur).
 */

import {
  Area,
  AreaChart,
  ResponsiveContainer,
} from 'recharts';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import type { DimensionKey } from '@/types/domain';

export interface DimensionSparklineProps {
  /** Clé de la dimension (utilisée pour ARIA + clé Recharts). */
  dimension: DimensionKey;
  /** Libellé affiché (ex. "Bien-être"). */
  label: string;
  /** Valeur courante affichée à droite (généralement la moyenne 7 j). */
  value: string;
  /** Texte du delta (ex. "+0.3 σ vs 30 j" ou "—"). */
  delta: string;
  /** Si true, le delta est rendu en couleur success (sinon warning). */
  deltaPositive?: boolean;
  /** Série numérique à dessiner (ordre chronologique gauche → droite). */
  data: readonly number[];
  /** Couleur via une variable PDS (ex. "var(--info)"). */
  color: string;
}

export function DimensionSparkline({
  dimension,
  label,
  value,
  delta,
  deltaPositive = false,
  data,
  color,
}: DimensionSparklineProps) {
  const { t } = useTranslation();
  const chartData = data.map((v, i) => ({ i, v }));
  const gradientId = `dimspark-${dimension}`;

  return (
    <article
      className={cn(
        'glass rounded-lg p-4',
      )}
      aria-label={t('history.trendCard.ariaLabel', { label })}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
          {label}
        </p>
        <div className="text-right">
          <p className="font-display text-foreground text-xl font-bold tracking-tight leading-none">
            {value}
          </p>
          <p
            className={cn(
              'mt-1 text-xs font-medium',
              deltaPositive ? 'text-success' : 'text-warning',
            )}
          >
            {delta}
          </p>
        </div>
      </div>

      <div className="mt-3 h-16 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
          >
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="v"
              stroke={color}
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              isAnimationActive={false}
              dot={false}
              activeDot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}

export default DimensionSparkline;
