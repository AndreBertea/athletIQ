/**
 * Route /history — artboard 08.
 *
 * Source visuelle : `docs/result/claude-design/project/screens.jsx`
 * (composant `ScreenHistory`, l. 1205).
 *
 * Layout :
 *   1. TopBar (logo + pastille profil)
 *   2. Hero `bg-signature` : eyebrow Consistance + glass card avec
 *      ConsistencyHeatmap + StreakBadge.
 *   3. Section Tendances : 4 DimensionSparkline (bien-être, sommeil,
 *      jambes, motivation) sur fond surface.
 *   4. WeeklySummary footer.
 *   5. BottomNav.
 *
 * Comportement :
 *   - Sophie (30 entries) : heatmap remplie + sparklines riches.
 *   - Thomas (6 entries) : heatmap dégradée (bcp de gris) + sparklines
 *     courts (sur 6 points).
 *   - Marie (0) : la route ne devrait pas être atteinte (phase onboarding),
 *     mais on rend un état "Pas encore d'historique" si jamais elle y va.
 *
 * Deux exports :
 *   - `HistoryContent` (named) : contenu interne SANS AppShell, utilisé
 *     par TabsLayout (pager horizontal /home /history /profile).
 *   - `HistoryRoute` (default) : wrapper AppShell autour de HistoryContent,
 *     conservé pour rétro-compatibilité.
 */

import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { AppShell } from '@/components/shared/AppShell';
import { ConsistencyHeatmap } from '@/components/history/ConsistencyHeatmap';
import { DimensionSparkline } from '@/components/history/DimensionSparkline';
import { StreakBadge } from '@/components/history/StreakBadge';
import { WeeklySummary } from '@/components/history/WeeklySummary';
import { useAuth } from '@/contexts/AuthContext';
import { useHistory } from '@/hooks/useHistory';
import {
  DIMENSION_KEYS,
  type DimensionKey,
  type ReadinessEntry,
} from '@/types/domain';

const DIMENSION_COLOR: Record<DimensionKey, string> = {
  wellbeing: 'var(--info)',
  sleep_quality: 'var(--brand-cyan)',
  legs: 'var(--brand-lavender)',
  motivation: 'var(--success)',
};

export function HistoryContent() {
  const { t } = useTranslation();
  const history = useHistory(30);
  const entries = useMemo<readonly ReadinessEntry[]>(
    () => history.data ?? [],
    [history.data],
  );

  // 4 séries sparkline dérivées des entries (chronologiques).
  const series = useMemo(() => {
    const chronological = [...entries].reverse();
    const out: Record<DimensionKey, number[]> = {
      wellbeing: [],
      sleep_quality: [],
      legs: [],
      motivation: [],
    };
    for (const e of chronological) {
      out.wellbeing.push(e.wellbeing);
      out.sleep_quality.push(e.sleep_quality);
      out.legs.push(e.legs);
      out.motivation.push(e.motivation);
    }
    return out;
  }, [entries]);

  const trends = useMemo(() => {
    return DIMENSION_KEYS.map((dim) => {
      const values = series[dim];
      const last7 = values.slice(-7);
      const prev7 = values.slice(-14, -7);
      const avg = (arr: number[]) =>
        arr.length === 0 ? null : arr.reduce((a, b) => a + b, 0) / arr.length;
      const cur = avg(last7);
      const previous = avg(prev7);
      const delta = cur != null && previous != null ? cur - previous : null;
      return { dim, values, cur, delta };
    });
  }, [series]);

  return (
    <div>
      {/* Hero */}
      <header className="bg-signature border-border-subtle border-b px-4 py-6">
        <p className="text-xs font-medium tracking-widest uppercase text-muted-foreground">
          {t('history.consistency')}
        </p>
        <div className="glass mt-3 rounded-lg p-4">
          {history.isLoading ? (
            <HeatmapSkeleton />
          ) : (
            <ConsistencyHeatmap entries={entries} />
          )}
        </div>
        <div className="mt-4">
          <StreakBadge
            totalEntries={entries.length}
            variant="on-signature"
          />
        </div>
      </header>

      {/* Tendances */}
      <section className="px-4 py-6">
        <p className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
          {t('history.trends')}
        </p>
        <div className="mt-3 flex flex-col gap-3">
          {trends.map(({ dim, values, cur, delta }) => {
            const label = t(`history.dimensions.${dim}`);
            const value = cur === null ? '—' : cur.toFixed(1);
            const deltaLabel =
              delta === null
                ? t('history.trendCard.deltaUnavailable')
                : t('history.trendCard.delta', {
                    value: `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}`,
                  });
            return (
              <DimensionSparkline
                key={dim}
                dimension={dim}
                label={label}
                value={value}
                delta={deltaLabel}
                deltaPositive={delta !== null && delta >= 0}
                data={values.length > 0 ? values : [0, 0]}
                color={DIMENSION_COLOR[dim]}
              />
            );
          })}
        </div>

        <div className="mt-6">
          <WeeklySummary entries={entries} />
        </div>

        {entries.length === 0 ? (
          <p className="text-muted-foreground mt-6 text-center text-sm">
            {t('history.empty')}
          </p>
        ) : null}
      </section>
    </div>
  );
}

export default function HistoryRoute() {
  const { user } = useAuth();
  const initial = user?.displayName.charAt(0) ?? 'M';
  return (
    <AppShell topBarProps={{ initial }}>
      <HistoryContent />
    </AppShell>
  );
}

function HeatmapSkeleton() {
  // Placeholder visuel le temps que la query résolve.
  return (
    <div
      className="grid gap-1"
      style={{ gridTemplateColumns: 'repeat(10, minmax(0, 1fr))' }}
    >
      {Array.from({ length: 30 }).map((_, i) => (
        <div
          key={i}
          className="border-border-subtle bg-surface-2/60 aspect-square rounded-sm border"
        />
      ))}
    </div>
  );
}
