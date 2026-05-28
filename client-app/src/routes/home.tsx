/**
 * Route /home — page d'accueil mobile.
 *
 * Le contenu suit le prototype AGON dans `/client-app/agon` :
 * Analytics, readiness/check-in, puis activités récentes. Le shell conserve
 * les données réelles déjà branchées.
 */

import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useReadinessScore } from '@/hooks/useReadinessScore';
import { useTodayEntry } from '@/hooks/useTodayEntry';
import { useAuth } from '@/contexts/AuthContext';
import { ActivitySummaryRow } from '@/components/activity/ActivitySummaryRow';
import { MobileAnalyticsDashboard } from '@/components/home/MobileAnalyticsDashboard';
import { AppShell } from '@/components/shared/AppShell';
import { useInsightText } from '@/i18n/useInsightText';
import { CALIBRATION_DAYS } from '@/lib/score/baseline';
import { activityDisplayId, agonApi, type EnrichedActivity } from '@/lib/api/agon';
import { cn } from '@/lib/utils';
import type { DimensionScore, ZColor } from '@/types/domain';

/**
 * Contenu interne /home — sans AppShell. Utilisé tel quel par TabsLayout.
 */
export function HomeContent() {
  const { scoreResult, isLoading, hasTodayEntry } = useReadinessScore();
  const todayEntry = useTodayEntry();
  const activitiesQuery = useQuery({
    queryKey: ['agon', 'recent-activities', 4],
    queryFn: () =>
      agonApi.getEnrichedActivities({ page: 1, per_page: 4, date_from: oneYearAgo() }),
    staleTime: 2 * 60_000,
  });

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-5 px-4 pb-6 pt-3">
      <MobileAnalyticsDashboard />

      <SectionSeparator />

      <section className="flex flex-col gap-3">
        <CheckinStatusCard
          hasEntry={hasTodayEntry}
          createdAt={todayEntry.data?.created_at ?? todayEntry.data?.updated_at ?? null}
        />

        {isLoading ? (
          <LoadingShimmer />
        ) : scoreResult.calibrated ? (
          <StableSection />
        ) : (
          <CalibrationSection />
        )}
      </section>

      <SectionSeparator />

      <RecentActivities
        activities={activitiesQuery.data?.items ?? []}
        loading={activitiesQuery.isLoading}
      />

      {/* todayEntry exposed pour debug / hydratation future. */}
      <span aria-hidden className="hidden">
        {todayEntry.data?.entry_date ?? ''}
      </span>
    </div>
  );
}

export default function HomeRoute() {
  const { user } = useAuth();
  const initial = initialOf(user?.displayName ?? 'A');
  return (
    <AppShell topBarProps={{ initial }}>
      <HomeContent />
    </AppShell>
  );
}

function CheckinStatusCard({
  hasEntry,
  createdAt,
}: {
  hasEntry: boolean;
  createdAt: string | null;
}) {
  const time = createdAt
    ? new Date(createdAt).toLocaleTimeString('fr-FR', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : null;

  if (hasEntry) {
    return (
      <div className="border-success/25 flex items-center gap-2.5 rounded-md border bg-success-bg px-3.5 py-2.5">
        <CheckCircle2 className="h-4 w-4 shrink-0 text-success" aria-hidden />
        <div className="min-w-0">
          <p className="text-[13px] font-semibold leading-tight text-success-fg">
            Check-in effectué{time ? ` à ${time}` : ''}
          </p>
          <p className="mt-0.5 text-[11px] leading-tight text-muted-foreground">
            Indicateurs mis à jour
          </p>
        </div>
      </div>
    );
  }

  return (
    <Link
      to="/checkin"
      className="flex items-center justify-between rounded-md border border-border-subtle bg-card px-3.5 py-3 transition active:bg-white/10"
    >
      <div>
        <p className="text-[13px] font-semibold leading-tight text-foreground">
          Faire son check-in
        </p>
        <p className="mt-1 text-[11px] leading-tight text-muted-foreground">
          60 sec · 4 questions sur ton état du jour
        </p>
      </div>
      <span className="rounded-full bg-brand-primary px-3 py-1 text-[11px] font-semibold text-foreground">
        Ouvrir
      </span>
    </Link>
  );
}

function RecentActivities({
  activities,
  loading,
}: {
  activities: EnrichedActivity[];
  loading: boolean;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-eyebrow">Activités récentes</p>
        <Link
          to="/activities"
          className="flex items-center gap-1 text-xs font-semibold text-brand-cyan"
        >
          Voir tout <ChevronRight className="h-3.5 w-3.5" />
        </Link>
      </div>
      <div className="overflow-hidden rounded-md border border-border-subtle bg-card">
        {loading ? (
          <div className="p-4 text-sm text-muted-foreground">
            Chargement des activités...
          </div>
        ) : activities.length === 0 ? (
          <div className="p-4 text-sm text-muted-foreground">
            Aucune activité Garmin récente.
          </div>
        ) : (
          activities.map((activity, index) => (
            <ActivitySummaryRow
              key={activityDisplayId(activity)}
              activity={activity}
              isLast={index === activities.length - 1}
              variant="home"
            />
          ))
        )}
      </div>
    </section>
  );
}

// ─── Calibration (J<14) — artboard 06 ───────────────────────────────────

function CalibrationSection() {
  const { scoreResult } = useReadinessScore();
  const progress = Math.min(
    100,
    Math.round((scoreResult.daysRecorded / CALIBRATION_DAYS) * 100),
  );
  const remaining = Math.max(0, CALIBRATION_DAYS - scoreResult.daysRecorded);

  return (
    <div className="rounded-md border border-border-subtle bg-card p-3.5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-eyebrow mb-1">Readiness en calibration</p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Encore {remaining} j. pour stabiliser la baseline personnelle.
          </p>
        </div>
        <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-semibold text-foreground">
          {scoreResult.daysRecorded}/{CALIBRATION_DAYS} j.
        </span>
      </div>

      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-3)]">
        <div
          className="h-full rounded-full bg-brand-primary transition-all"
          style={{ width: `${progress}%` }}
        />
      </div>

      {scoreResult.dimensions.length > 0 ? (
        <div className="mt-4">
          <p className="text-eyebrow mb-2">Aujourd'hui</p>
          <CompactDimensionList dimensions={scoreResult.dimensions} />
        </div>
      ) : null}
    </div>
  );
}

// ─── Stable (J≥14) — artboard 07-B ──────────────────────────────────────

function StableSection() {
  const { t } = useTranslation();
  const { scoreResult } = useReadinessScore();
  const renderInsight = useInsightText();
  const insightText = renderInsight(scoreResult.insight);
  const score = scoreResult.score ?? 0;
  const delta = scoreResult.delta;
  const deltaTone =
    scoreResult.color === 'green'
      ? 'text-success'
      : scoreResult.color === 'orange'
        ? 'text-warning'
        : 'text-danger';

  return (
    <div className="rounded-md border border-border-subtle bg-card p-3.5">
      <div className="mb-3.5 flex items-center gap-3">
        <CompactScoreGauge score={score} color={scoreResult.color} />
        <div className="flex-1">
          <p className="text-eyebrow mb-1.5">{t('home.stable.vsBaselineEyebrow')}</p>
          <p
            className={`font-display text-[30px] font-bold leading-none tracking-tight ${deltaTone}`}
          >
            {formatDelta(delta)}
          </p>
          <p className="mt-1 font-text text-[11px] leading-tight text-muted-foreground">
            {t('home.stable.rangeNote')}
          </p>
          <span className={statusPillClass(scoreResult.color)}>
            {statusLabel(scoreResult.color)}
          </span>
        </div>
      </div>

      {insightText ? (
        <div className="mb-3.5 rounded-md border border-border-subtle bg-muted px-3 py-2.5">
          <p className="text-xs italic leading-relaxed text-muted-foreground">
            {insightText}
          </p>
        </div>
      ) : null}

      {scoreResult.dimensions.length > 0 ? (
        <div>
          <p className="text-eyebrow mb-2">{t('home.stable.decompositionEyebrow')}</p>
          <CompactDimensionList dimensions={scoreResult.dimensions} />
        </div>
      ) : null}
    </div>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────

function SectionSeparator() {
  return <div className="h-px w-full bg-border-subtle" aria-hidden />;
}

function CompactScoreGauge({ score, color }: { score: number; color: ZColor }) {
  const radius = 33;
  const circumference = 2 * Math.PI * radius;
  const progress = Math.max(0, Math.min(100, score));
  const dash = (progress / 100) * circumference;
  const strokeClass =
    color === 'green'
      ? 'stroke-success'
      : color === 'orange'
        ? 'stroke-warning'
        : 'stroke-danger';

  return (
    <div className="relative grid h-20 w-20 shrink-0 place-items-center">
      <svg className="-rotate-90" width="80" height="80" viewBox="0 0 80 80" aria-hidden>
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke="rgba(245,239,224,0.08)"
          strokeWidth="7"
        />
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          className={strokeClass}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference - dash}`}
        />
      </svg>
      <div className="absolute text-center">
        <p className="font-display text-[22px] font-bold leading-none text-foreground">
          {Math.round(score)}
        </p>
        <p className="mt-0.5 text-[9px] font-semibold uppercase text-muted-foreground">
          score
        </p>
      </div>
    </div>
  );
}

function CompactDimensionList({ dimensions }: { dimensions: DimensionScore[] }) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2.5">
      {dimensions.map((dimension) => {
        const progress = Math.max(0, Math.min(100, (dimension.value / 5) * 100));
        return (
          <div key={dimension.key}>
            <div className="mb-1 flex items-center justify-between gap-2">
              <p className="flex min-w-0 items-center gap-1.5 text-xs font-semibold text-foreground">
                <span aria-hidden>{dimensionIcon(dimension.key)}</span>
                <span className="truncate">
                  {capitalize(t(`home.dimensionLabels.${dimension.key}`))}
                </span>
              </p>
              <span className="text-[11px] font-semibold text-muted-foreground">
                {dimension.value}/5
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-3)]">
              <div
                className={cn('h-full rounded-full', dimensionFillClass(dimension.color))}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function LoadingShimmer() {
  return (
    <div className="rounded-md border border-border-subtle bg-card p-3.5">
      <div className="h-20 animate-pulse rounded-md bg-muted" />
      <div className="mt-3 space-y-2">
        <div className="h-2 animate-pulse rounded-full bg-muted" />
        <div className="h-2 w-3/4 animate-pulse rounded-full bg-muted" />
      </div>
    </div>
  );
}

function statusLabel(color: ZColor): string {
  switch (color) {
    case 'green':
      return 'Bonne forme';
    case 'orange':
      return 'Attention';
    case 'red':
      return 'Récupération';
  }
}

function statusPillClass(color: ZColor): string {
  return cn(
    'mt-2 inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold',
    color === 'green' && 'bg-success-bg text-success-fg',
    color === 'orange' && 'bg-warning-bg text-warning-fg',
    color === 'red' && 'bg-danger-bg text-danger-fg',
  );
}

function dimensionFillClass(color: ZColor): string {
  if (color === 'green') return 'bg-success';
  if (color === 'orange') return 'bg-warning';
  return 'bg-danger';
}

function dimensionIcon(key: DimensionScore['key']): string {
  switch (key) {
    case 'wellbeing':
      return '🙂';
    case 'sleep_quality':
      return '🛏️';
    case 'legs':
      return '🦵';
    case 'motivation':
      return '⚡';
  }
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function formatDelta(delta: number | null): string {
  if (delta === null) return '—';
  if (delta === 0) return '0';
  if (delta > 0) return `+${delta}`;
  return `−${Math.abs(delta)}`;
}

function oneYearAgo(): string {
  const date = new Date();
  date.setFullYear(date.getFullYear() - 1);
  return date.toISOString().slice(0, 10);
}

function initialOf(name: string): string {
  return name.trim().charAt(0).toUpperCase() || 'A';
}
