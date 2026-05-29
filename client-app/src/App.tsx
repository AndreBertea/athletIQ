/**
 * App.tsx — router + guards globaux (AGON PWA cliente).
 *
 * Routing post-login :
 *   - `/`              : auth (login + signup + démo)
 *   - `/onboarding`    : wizard 3 écrans (profil tout juste créé)
 *   - `/home`          : page « aujourd'hui » (score / calibration).
 *                        Hub principal. Sans profile → /onboarding.
 *   - `/checkin`       : saisie quotidienne. Submit success → navigate /home.
 *   - `/profile`       : préférences + intégrations wearables.
 *   - `/live`          : page principale du Live tracking (sélecteur de session).
 *   - `/live/shared`   : sessions partagées (entrée publique / coach).
 *   - `/live/:id`      : détail d'une session Live en cours / passée.
 *
 * Le checkin-done legacy est redirigé vers /home.
 *
 * RouteDispatcher (V3 — MVP AGON) :
 *   - !user                                                  → /
 *   - user && !profile && pathname !== '/onboarding'         → /onboarding
 *   - sinon                                                  → <Outlet />
 *
 * Le reroute /home → /checkin (forçage de la saisie quotidienne) a été
 * retiré pour le MVP. L'utilisateur peut consulter /home, /profile et
 * /live librement ; il doit déclencher /checkin explicitement.
 *
 * Lazy loading des routes Live : les composants `routes/live*.tsx`
 * seront ajoutés ultérieurement ; les imports lazy ici préparent le
 * routing sans bloquer les builds des autres routes.
 */

import React, { Suspense } from 'react';
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { useProfile } from '@/hooks/useProfile';
import { supabase } from '@/lib/supabase';
import { ErrorBoundary } from '@/components/shared/ErrorBoundary';
import { PageTransition } from '@/components/shared/PageTransition';
import AuthRoute from '@/routes/auth';
import OnboardingRoute from '@/routes/onboarding';
import CheckinRoute from '@/routes/checkin';
import HomeRoute from '@/routes/home';
import ProfileRoute from '@/routes/profile';
import ActivitiesRoute from '@/routes/activities';
import ActivityDetailRoute from '@/routes/activity-detail';

// Live tracking : composants créés au fil du MVP. Le code-splitting via
// React.lazy permet d'isoler le bundle Live (carto / WebSocket) du reste
// de l'app — non chargé tant que l'utilisateur ne visite pas /live*.
const Live = React.lazy(() => import('./routes/live'));
const LiveShared = React.lazy(() => import('./routes/live-shared'));
const LiveSession = React.lazy(() => import('./routes/live-session'));
const RacePredictor = React.lazy(() => import('./routes/race-predictor'));

export default function App() {
  return (
    <AuthProvider>
      <RealtimeBridge />
      <BrowserRouter>
        <ErrorBoundary>
          <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/" element={<AuthRoute />} />
              <Route element={<RequireAuth />}>
                <Route element={<RouteDispatcher />}>
                  <Route path="/onboarding" element={<OnboardingRoute />} />
                  <Route path="/checkin" element={<CheckinRoute />} />
                  {/* Legacy : /checkin-done redirige vers /home. */}
                  <Route
                    path="/checkin-done"
                    element={<Navigate to="/home" replace />}
                  />
                  <Route path="/home" element={<HomeRoute />} />
                  <Route path="/activities" element={<ActivitiesRoute />} />
                  <Route path="/activities/:id" element={<ActivityDetailRoute />} />
                  <Route path="/profile" element={<ProfileRoute />} />
                  <Route path="/settings" element={<Navigate to="/profile" replace />} />
                  <Route path="/race-predictor" element={<RacePredictor />} />
                  {/* Live tracking — 3 routes lazy-loadées. */}
                  <Route path="/live" element={<Live />} />
                  <Route path="/live/shared" element={<LiveShared />} />
                  <Route path="/live/:id" element={<LiveSession />} />
                </Route>
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </BrowserRouter>
    </AuthProvider>
  );
}

function RealtimeBridge() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  React.useEffect(() => {
    if (!user) return undefined;

    const channel = supabase
      .channel(`agon-jobs-${user.id}`)
      .on(
        'postgres_changes',
        {
          event: '*',
          schema: 'public',
          table: 'sync_jobs',
          filter: `user_id=eq.${user.id}`,
        },
        () => {
          void queryClient.invalidateQueries({ queryKey: ['agon'] });
          void queryClient.invalidateQueries({ queryKey: ['readiness'] });
        },
      )
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'job_events',
          filter: `user_id=eq.${user.id}`,
        },
        () => {
          void queryClient.invalidateQueries({ queryKey: ['agon'] });
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [queryClient, user]);

  return null;
}

function RequireAuth() {
  const { user, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) return <RouteFallback />;
  if (!user) {
    return <Navigate to="/" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/**
 * RouteDispatcher — guard global post-auth.
 *
 * MVP : on se contente d'imposer l'onboarding au premier login. Aucun
 * rerouting forcé vers /checkin (l'utilisateur navigue librement entre
 * /home, /profile et /live).
 */
function RouteDispatcher() {
  const location = useLocation();
  const profileQuery = useProfile();

  // Bloque le rendu tant que profile n'est pas résolu pour éviter un
  // flash de /home avant le reroute /onboarding.
  if (profileQuery.isLoading) return <RouteFallback />;

  if (!profileQuery.data && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />;
  }

  return <PageTransition />;
}

function RouteFallback() {
  const { t } = useTranslation();
  return (
    <main className="bg-signature flex h-dvh w-full items-center justify-center">
      <span className="text-muted-foreground text-xs tracking-widest uppercase">
        {t('common.loading')}
      </span>
    </main>
  );
}
