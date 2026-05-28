import { useQuery } from '@tanstack/react-query';
import { Filter, RefreshCw } from 'lucide-react';
import { ActivitySummaryRow } from '@/components/activity/ActivitySummaryRow';
import { AppShell } from '@/components/shared/AppShell';
import { activityDisplayId, agonApi, oneYearAgoIsoDate } from '@/lib/api/agon';

export default function ActivitiesRoute() {
  const activitiesQuery = useQuery({
    queryKey: ['agon', 'activities', 'list', oneYearAgoIsoDate()],
    queryFn: () => agonApi.getEnrichedActivities({
      page: 1,
      per_page: 100,
      date_from: oneYearAgoIsoDate(),
    }),
    staleTime: 2 * 60_000,
  });

  const activities = activitiesQuery.data?.items ?? [];

  return (
    <AppShell topBarProps={{ back: true }}>
      <div className="mx-auto w-full max-w-md px-4 pt-4 pb-8">
        <header className="mb-5">
          <p className="text-eyebrow mb-2">Garmin · 1 an</p>
          <h1 className="text-foreground font-display text-2xl font-bold tracking-tight">
            Activites
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Toutes les activites synchronisees, enrichies FIT et meteo quand disponible.
          </p>
        </header>

        <div className="mb-3 flex items-center justify-between rounded-md border border-border-subtle bg-card px-3 py-2">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Filter className="h-4 w-4 text-brand-cyan" />
            {activities.length} activite{activities.length > 1 ? 's' : ''}
          </div>
          <button
            type="button"
            onClick={() => void activitiesQuery.refetch()}
            className="text-muted-foreground rounded-full p-1 hover:text-foreground"
            aria-label="Rafraichir"
          >
            <RefreshCw className={`h-4 w-4 ${activitiesQuery.isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="overflow-hidden rounded-md border border-border-subtle bg-card">
          {activitiesQuery.isLoading ? (
            <div className="p-4 text-sm text-muted-foreground">Chargement…</div>
          ) : activities.length === 0 ? (
            <div className="p-4 text-sm text-muted-foreground">Aucune activite Garmin sur la periode.</div>
          ) : (
            activities.map((activity, index) => (
              <ActivitySummaryRow
                key={activityDisplayId(activity)}
                activity={activity}
                isLast={index === activities.length - 1}
                variant="list"
              />
            ))
          )}
        </div>
      </div>
    </AppShell>
  );
}
