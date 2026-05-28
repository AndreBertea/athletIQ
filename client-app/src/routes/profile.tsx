/**
 * Route /profile — artboard 09.
 *
 * Source visuelle : `docs/result/claude-design/project/screens.jsx`
 * (composant `ScreenProfile`, l. 1294).
 *
 * Sections :
 *   1. Header : avatar + nom + email mockée.
 *   2. Notifications : heure de check-in (lecture profile.notif_local_time)
 *      + bouton Pause 7 jours (V1 : visuel uniquement, pas de side-effect).
 *   3. Affichage : toggle "Afficher mon score" (déjà géré par le gating
 *      J14, mais l'utilisateur peut masquer) + toggle streak.
 *   4. Données / Intégrations : 2 cards (Apple Health / Garmin) qui
 *      ouvrent ComingSoonModal. Whoop et Oura retirés en V1.
 *   5. Compte : Se déconnecter → signOut() + redirect /.
 *
 * Deux exports :
 *   - `ProfileContent` (named) : contenu interne SANS AppShell, utilisé
 *     par TabsLayout (pager horizontal /home /history /profile).
 *   - `ProfileRoute` (default) : wrapper AppShell autour de ProfileContent,
 *     conservé pour rétro-compatibilité.
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, CheckCircle, Download, RefreshCw, ShieldCheck, Trash2, Watch } from 'lucide-react';
import { AppShell } from '@/components/shared/AppShell';
import {
  ComingSoonModal,
  WEARABLE_SERVICES,
  type WearableService,
} from '@/components/profile/ComingSoonModal';
import { useAuth } from '@/contexts/AuthContext';
import { useProfile } from '@/hooks/useProfile';
import { useUpdateProfile } from '@/hooks/useUpdateProfile';
import { LanguageSwitcher } from '@/i18n/LanguageSwitcher';
import { agonApi } from '@/lib/api/agon';
import {
  DEFAULT_IMPORT_DAYS_BACK,
  IMPORT_PERIOD_OPTIONS,
  formatImportPeriod,
  getGarminImportState,
  shortImportPeriod,
  startGarminImport,
  useGarminImportJob,
  type GarminImportState,
} from '@/lib/garmin-import-job';
import { cn } from '@/lib/utils';
import type { Profile } from '@/types/domain';

export function ProfileContent() {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const profileQuery = useProfile();
  const updateProfile = useUpdateProfile();
  const queryClient = useQueryClient();
  const [activeService, setActiveService] = useState<WearableService | null>(null);
  const [paused, setPaused] = useState(false);
  const [garminEmail, setGarminEmail] = useState('');
  const [garminPassword, setGarminPassword] = useState('');
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);
  const [garminMfaCode, setGarminMfaCode] = useState('');
  const [garminNeedsMfa, setGarminNeedsMfa] = useState(false);
  const [importDaysBack, setImportDaysBack] = useState(() => {
    const currentImport = getGarminImportState();
    return currentImport.daysBack ?? DEFAULT_IMPORT_DAYS_BACK;
  });
  const importState = useGarminImportJob();

  const profile: Profile | null = profileQuery.data ?? null;
  const displayName = user?.displayName ?? user?.fullName ?? '—';
  const initial = (displayName !== '—' ? displayName.charAt(0) : '?').toUpperCase();
  // Email = email reel du compte FastAPI (plus de forge enduraw.fr).
  const email = user?.email ?? profile?.email ?? '—';
  const notifTime = profile?.notif_local_time
    ? formatTimeShort(profile.notif_local_time)
    : '07:30';
  const streakVisible = profile?.streak_visible ?? true;
  // V1 : "afficher mon score" est inféré (toujours true pour les phases stable+).
  // On expose un toggle local cosmétique en attendant un vrai champ profil.
  const [scoreVisible, setScoreVisible] = useState(true);
  // V1 : toggle local "Notifications on/off". Si off, on cache les
  // sous-réglages (heure, pause). En V1.1 ça sera un vrai champ profile.
  const [notifEnabled, setNotifEnabled] = useState(true);
  const garminStatus = useQuery({
    queryKey: ['agon', 'garmin-status'],
    queryFn: () => agonApi.getGarminStatus(),
    staleTime: 30_000,
  });
  const enrichmentStatus = useQuery({
    queryKey: ['agon', 'garmin-enrichment-status'],
    queryFn: () => agonApi.getGarminEnrichmentStatus(),
    staleTime: 60_000,
  });
  const weatherStatus = useQuery({
    queryKey: ['agon', 'weather-status'],
    queryFn: () => agonApi.getWeatherStatus(),
    staleTime: 60_000,
  });

  const garminLogin = useMutation({
    mutationFn: () => agonApi.loginGarmin(garminEmail, garminPassword, garminMfaCode),
    onSuccess: (result) => {
      if (result.needs_mfa) {
        setGarminNeedsMfa(true);
        setSettingsMessage('Code Garmin MFA requis.');
        return;
      }
      setGarminPassword('');
      setGarminMfaCode('');
      setGarminNeedsMfa(false);
      setSettingsMessage('Garmin connecte.');
      void queryClient.invalidateQueries({ queryKey: ['agon'] });
    },
    onError: (error) => setSettingsMessage(error instanceof Error ? error.message : 'Connexion Garmin impossible.'),
  });
  const disconnectGarmin = useMutation({
    mutationFn: () => agonApi.disconnectGarmin(),
    onSuccess: () => {
      setSettingsMessage('Garmin deconnecte.');
      void queryClient.invalidateQueries({ queryKey: ['agon'] });
    },
  });

  useEffect(() => {
    if (importState.status === 'success') {
      void queryClient.invalidateQueries({ queryKey: ['agon'] });
    }
  }, [importState, queryClient]);
  const deleteAllData = useMutation({
    mutationFn: () => agonApi.deleteAllUserData(),
    onSuccess: () => {
      setSettingsMessage('Donnees supprimees. Le compte est conserve.');
      void queryClient.invalidateQueries();
    },
  });

  const handleStreakToggle = (next: boolean) => {
    if (!profile) return;
    updateProfile.mutate({ patch: { streak_visible: next } });
  };

  const handleSignOut = async () => {
    await signOut();
    navigate('/', { replace: true });
  };

  return (
    <>
      <div className="pt-2 pb-4">
        {/* Header utilisateur */}
        <div className="flex items-center gap-4 px-4 py-4">
          <div
            className={cn(
              'bg-brand-primary flex h-16 w-16 items-center justify-center rounded-full',
              'text-foreground font-semibold text-2xl',
            )}
          >
            {initial}
          </div>
          <div>
            <p className="font-display text-foreground text-xl font-bold tracking-tight">
              {displayName}
            </p>
            <p className="text-muted-foreground mt-1 text-xs">{email}</p>
          </div>
        </div>

        {/* Section Langue — sélecteur drapeaux 🇫🇷 / 🇬🇧. Persistance
            via i18n-browser-languagedetector (clé `enduraw.lang`). */}
        <Section title={t('profile.sections.language')}>
          <div className="flex w-full items-center justify-between px-4 py-3">
            <p className="text-foreground text-sm font-medium">
              {t('language.label')}
            </p>
            <LanguageSwitcher size="md" />
          </div>
        </Section>

        {/* Section Notifications — toggle maître + sous-réglages
            conditionnels. Off → on masque heure + pause ; on → 3 lignes. */}
        <Section title={t('profile.sections.notifications')}>
          <SettingsRow
            label={t('profile.rows.notifications.label')}
            hint={t('profile.rows.notifications.hint')}
            isLast={!notifEnabled}
            right={<Toggle on={notifEnabled} onChange={setNotifEnabled} />}
          />
          {notifEnabled ? (
            <>
              <SettingsRow
                label={t('profile.rows.checkinTime.label')}
                right={
                  <input
                    type="time"
                    value={notifTime}
                    onChange={(e) => {
                      const next = e.target.value; // 'HH:MM'
                      if (!profile || !next) return;
                      updateProfile.mutate({
                        patch: { notif_local_time: `${next}:00` },
                      });
                    }}
                    aria-label={t('profile.rows.checkinTime.ariaLabel')}
                    className={cn(
                      'font-display text-brand-cyan text-base font-semibold tracking-tight',
                      // bg transparent + appearance reset pour ne PAS afficher
                      // le chrome WebKit (badge "horloge", clear button) ;
                      // colorScheme dark force le picker iOS en mode sombre.
                      'cursor-pointer bg-transparent focus:outline-none',
                      'appearance-none [&::-webkit-calendar-picker-indicator]:hidden',
                    )}
                    style={{ colorScheme: 'dark' }}
                  />
                }
              />
              <SettingsRow
                label={t('profile.rows.pause.label')}
                hint={t('profile.rows.pause.hint')}
                isLast
                right={
                  <button
                    type="button"
                    onClick={() => setPaused((p) => !p)}
                    className={cn(
                      'border-border h-8 rounded-full border px-3 text-xs font-semibold transition',
                      paused
                        ? 'bg-brand-primary text-foreground border-brand-primary'
                        : 'text-foreground hover:bg-white/5',
                    )}
                  >
                    {paused
                      ? t('profile.rows.pause.active')
                      : t('profile.rows.pause.activate')}
                  </button>
                }
              />
            </>
          ) : null}
        </Section>

        {/* Section Affichage */}
        <Section
          title={t('profile.sections.display')}
          note={t('profile.sections.displayNote')}
        >
          <SettingsRow
            label={t('profile.rows.scoreVisible.label')}
            hint={t('profile.rows.scoreVisible.hint')}
            right={<Toggle on={scoreVisible} onChange={setScoreVisible} />}
          />
          <SettingsRow
            label={t('profile.rows.streakVisible.label')}
            hint={t('profile.rows.streakVisible.hint')}
            isLast
            right={
              <Toggle
                on={streakVisible}
                onChange={(next) => handleStreakToggle(next)}
                disabled={updateProfile.isPending || !profile}
              />
            }
          />
        </Section>

        {/* Section Intégrations */}
        <Section title={t('profile.sections.integrations')}>
          <GarminSettings
            connected={garminStatus.data?.connected === true}
            email={garminEmail}
            password={garminPassword}
            mfaCode={garminMfaCode}
            needsMfa={garminNeedsMfa}
            onEmailChange={setGarminEmail}
            onPasswordChange={setGarminPassword}
            onMfaCodeChange={setGarminMfaCode}
            onConnect={() => garminLogin.mutate()}
            onDisconnect={() => disconnectGarmin.mutate()}
            onImport={() => void startGarminImport(importDaysBack).catch(() => undefined)}
            importDaysBack={importDaysBack}
            onImportDaysBackChange={setImportDaysBack}
            loading={garminLogin.isPending || importState.status === 'running' || disconnectGarmin.isPending}
            importState={importState}
            enrichedCount={enrichmentStatus.data?.enriched_activities ?? null}
            pendingFit={enrichmentStatus.data?.pending_activities ?? null}
            weatherCount={weatherStatus.data?.with_weather ?? null}
            weatherEligible={weatherStatus.data?.eligible_weather_activities ?? weatherStatus.data?.with_coordinates ?? null}
            weatherTimelineCount={weatherStatus.data?.with_weather_timeline ?? null}
          />
          {(Object.keys(WEARABLE_SERVICES) as WearableService[]).map(
            (svc, idx, arr) => {
              if (svc === 'garmin' || svc === 'apple_health') return null;
              return (
                <SettingsRow
                  key={svc}
                  label={t(`profile.integrations.${svc}.label`)}
                  hint={t(`profile.integrations.${svc}.description`)}
                  isLast={idx === arr.length - 1}
                  onClick={() => setActiveService(svc)}
                  right={
                    <span className="rounded-full bg-white/5 px-2 py-1 text-[11px] font-medium text-muted-foreground">
                      {t('profile.integrations.soonBadge')}
                    </span>
                  }
                />
              );
            },
          )}
        </Section>

        <Section title="Données et confidentialité">
          <SettingsRow
            label="Exporter mes donnees"
            hint="Telecharge un export JSON conforme RGPD."
            right={<Download className="h-4 w-4 text-brand-cyan" />}
            onClick={() => void exportData()}
          />
          <SettingsRow
            label="Supprimer mes donnees"
            hint="Supprime les donnees sportives et analyses, sans supprimer le compte."
            danger
            right={<Trash2 className="h-4 w-4 text-danger" />}
            onClick={() => {
              if (window.confirm('Supprimer toutes tes donnees sportives ?')) {
                deleteAllData.mutate();
              }
            }}
          />
          <SettingsRow
            label="Garanties RGPD"
            hint="Export, suppression des donnees et suppression de compte sont exposes par l'API."
            isLast
            right={<ShieldCheck className="h-4 w-4 text-success" />}
          />
        </Section>

        {settingsMessage ? (
          <p className="mx-4 mb-4 rounded-md border border-border-subtle bg-card p-3 text-xs text-muted-foreground">
            {settingsMessage}
          </p>
        ) : null}

        {/* Section Compte */}
        <Section title={t('profile.sections.account')}>
          <SettingsRow
            label={t('profile.rows.signOut')}
            isLast
            danger
            onClick={handleSignOut}
          />
        </Section>

        <p className="text-muted-foreground text-center text-xs">
          {t('profile.version')}
        </p>
      </div>

      <ComingSoonModal
        service={activeService}
        onClose={() => setActiveService(null)}
      />
    </>
  );

  async function exportData() {
    const blob = await agonApi.exportUserData();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `agon_export_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }
}

export default function ProfileRoute() {
  const { user } = useAuth();
  const initial = user?.displayName.charAt(0) ?? 'M';
  return (
    <AppShell topBarProps={{ initial }}>
      <ProfileContent />
    </AppShell>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Composants intimes
// ────────────────────────────────────────────────────────────────────────

interface SectionProps {
  title: string;
  /** Annotation discrète à droite du titre (ex. "non fonctionnel"). */
  note?: string;
  children: React.ReactNode;
}

function Section({ title, note, children }: SectionProps) {
  return (
    <section className="mb-6 px-4">
      <p className="text-eyebrow flex items-baseline gap-2 pb-2">
        <span>{title}</span>
        {note ? (
          <span className="text-muted-foreground/60 text-[10px] font-normal tracking-normal normal-case">
            {note}
          </span>
        ) : null}
      </p>
      <div className="border-border-subtle bg-card overflow-hidden rounded-md border">
        {children}
      </div>
    </section>
  );
}

function GarminSettings({
  connected,
  email,
  password,
  mfaCode,
  needsMfa,
  onEmailChange,
  onPasswordChange,
  onMfaCodeChange,
  onConnect,
  onDisconnect,
  onImport,
  importDaysBack,
  onImportDaysBackChange,
  loading,
  importState,
  enrichedCount,
  pendingFit,
  weatherCount,
  weatherEligible,
  weatherTimelineCount,
}: {
  connected: boolean;
  email: string;
  password: string;
  mfaCode: string;
  needsMfa: boolean;
  onEmailChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onMfaCodeChange: (value: string) => void;
  onConnect: () => void;
  onDisconnect: () => void;
  onImport: () => void;
  importDaysBack: number;
  onImportDaysBackChange: (value: number) => void;
  loading: boolean;
  importState: GarminImportState;
  enrichedCount: number | null;
  pendingFit: number | null;
  weatherCount: number | null;
  weatherEligible: number | null;
  weatherTimelineCount: number | null;
}) {
  const weatherValue = weatherCount == null
    ? '—'
    : weatherEligible != null
      ? `${weatherCount}/${weatherEligible}`
      : String(weatherCount);
  const importRunning = importState.status === 'running';
  const importSucceeded = importState.status === 'success' && importState.daysBack === importDaysBack;
  const importErrored = importState.status === 'error' && importState.daysBack === importDaysBack;
  const importButtonLabel = importRunning
    ? 'Import en cours...'
    : importSucceeded
      ? 'Import termine'
      : importErrored
        ? 'Relancer'
        : `Importer ${shortImportPeriod(importDaysBack)}`;
  const periodStatus = importState.status === 'running'
    ? importState.progress
    : importState.status === 'success'
      ? importState.summary.finalStatus
      : null;
  const periodRecord = periodStatus as Record<string, unknown> | null;
  const periodActivities = readStatusNumber(periodRecord, 'totalActivities', 'total_activities');
  const periodFitDone = readStatusNumber(periodRecord, 'fitDone', 'fit_done');
  const periodFitTotal = readStatusNumber(periodRecord, 'fitTotal', 'fit_total');
  const periodWeatherDone = readStatusNumber(periodRecord, 'weatherDone', 'weather_done');
  const periodWeatherTotal = readStatusNumber(periodRecord, 'weatherTotal', 'weather_total');
  const periodFitPending = readStatusNumber(periodRecord, 'fitPending', 'fit_pending');
  const periodActivityValue = periodActivities == null ? '—' : String(periodActivities);
  const remainingValue = periodFitPending != null
    ? String(periodFitPending)
    : pendingFit == null
      ? '—'
      : String(pendingFit);
  const fitValue = periodFitDone != null && periodFitTotal != null
    ? `${periodFitDone}/${periodFitTotal}`
    : enrichedCount == null
      ? '—'
      : String(enrichedCount);
  const weatherPeriodValue = periodWeatherDone != null && periodWeatherTotal != null
    ? `${periodWeatherDone}/${periodWeatherTotal}`
    : weatherTimelineCount != null
      ? String(weatherTimelineCount)
      : weatherValue;

  return (
    <div className="border-border-subtle border-b p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-foreground flex items-center gap-2 text-sm font-semibold">
            <Watch className="h-4 w-4 text-brand-cyan" />
            Garmin Connect
          </p>
          <p className="text-muted-foreground mt-1 text-xs">
            {connected ? 'Connecte. Les identifiants ne sont pas stockes.' : 'Connexion one-time pour importer les donnees.'}
          </p>
        </div>
        <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${connected ? 'bg-success-bg text-success-fg' : 'bg-white/5 text-muted-foreground'}`}>
          {connected ? 'Actif' : 'A connecter'}
        </span>
      </div>

      {!connected ? (
        <div className="space-y-2">
          <input
            value={email}
            onChange={(event) => onEmailChange(event.target.value)}
            type="email"
            placeholder="Email Garmin"
            className="w-full rounded-md border border-border-subtle bg-surface-2 px-3 py-2 text-sm"
          />
          <input
            value={password}
            onChange={(event) => onPasswordChange(event.target.value)}
            type="password"
            placeholder="Mot de passe Garmin"
            className="w-full rounded-md border border-border-subtle bg-surface-2 px-3 py-2 text-sm"
          />
          {needsMfa ? (
            <input
              value={mfaCode}
              onChange={(event) => onMfaCodeChange(event.target.value)}
              inputMode="numeric"
              placeholder="Code Garmin MFA"
              className="w-full rounded-md border border-border-subtle bg-surface-2 px-3 py-2 text-sm"
            />
          ) : null}
          <button
            type="button"
            onClick={onConnect}
            disabled={loading || !email || !password || (needsMfa && !mfaCode)}
            className="btn-glass-primary w-full"
          >
            {needsMfa ? 'Valider le code Garmin' : 'Connecter Garmin'}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <label htmlFor="mobile-import-days" className="text-muted-foreground mb-1 block text-xs font-semibold">
              Duree d'import
            </label>
            <select
              id="mobile-import-days"
              value={importDaysBack}
              onChange={(event) => onImportDaysBackChange(Number(event.target.value))}
              disabled={loading}
              className="border-border-subtle bg-surface-2 text-foreground h-10 w-full rounded-md border px-3 text-sm font-semibold disabled:opacity-50"
            >
              {IMPORT_PERIOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
              L'app compte d'abord les activites Garmin de la periode, puis traite FIT et daily. La meteo 10 min se lance depuis le detail d'une activite.
            </p>
          </div>

          <div className="grid grid-cols-4 gap-2">
            <MiniStatus label="Activites" value={periodActivityValue} />
            <MiniStatus label="FIT" value={fitValue} />
            <MiniStatus label="Meteo 10m" value={weatherPeriodValue} />
            <MiniStatus label="Restant" value={remainingValue} />
          </div>
          {importState.status !== 'idle' ? <ImportStatusCard state={importState} /> : null}
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={onImport}
              disabled={loading}
              className={cn(
                'rounded-md px-3 py-2 text-sm font-semibold text-white disabled:opacity-50',
                importSucceeded ? 'bg-success' : importErrored ? 'bg-danger' : 'bg-brand-primary',
              )}
            >
              {importSucceeded ? (
                <CheckCircle className="mr-1 inline h-4 w-4" />
              ) : importErrored ? (
                <AlertTriangle className="mr-1 inline h-4 w-4" />
              ) : (
                <RefreshCw className={`mr-1 inline h-4 w-4 ${importRunning ? 'animate-spin' : ''}`} />
              )}
              {importButtonLabel}
            </button>
            <button type="button" onClick={onDisconnect} disabled={loading} className="rounded-md border border-border-subtle px-3 py-2 text-sm font-semibold text-muted-foreground disabled:opacity-50">
              Deconnecter
            </button>
          </div>
          <p className="text-muted-foreground text-[11px] leading-relaxed">
            L'import peut rester ouvert longtemps : le bouton continue a tourner apres navigation et une validation s'affiche quand les phases sont terminees.
          </p>
        </div>
      )}
    </div>
  );
}

function readStatusNumber(record: Record<string, unknown> | null, ...keys: string[]): number | null {
  if (!record) return null;
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return null;
}

function MiniStatus({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-surface-2 p-2 text-center">
      <p className="text-foreground text-sm font-bold">{value}</p>
      <p className="text-muted-foreground text-[10px]">{label}</p>
    </div>
  );
}

function ImportStatusCard({ state }: { state: GarminImportState }) {
  if (state.status === 'success') {
    const { finalStatus } = state.summary;
    const remaining = finalStatus.fit_pending;
    return (
      <div className="border-success/30 bg-success-bg rounded-md border px-3 py-2">
        <div className="flex items-center gap-2">
          <CheckCircle className="text-success h-3.5 w-3.5" />
          <p className="text-success-fg text-xs font-semibold">Import termine</p>
        </div>
        <p className="text-success-fg/80 mt-1 text-[11px]">
          {formatImportPeriod(state.daysBack)} · {finalStatus.total_activities} activite(s) · FIT {finalStatus.fit_done}/{finalStatus.fit_total}
        </p>
        <p className="text-success-fg/70 mt-1 text-[11px]">
          Meteo 10 min : {finalStatus.weather_done}/{finalStatus.weather_total}, a lancer depuis chaque activite si besoin.
        </p>
        {remaining > 0 ? (
          <p className="text-success-fg/70 mt-1 text-[11px]">
            {remaining} FIT restent a traiter, souvent faute de fichier exploitable.
          </p>
        ) : null}
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="border-danger/30 bg-danger/10 rounded-md border px-3 py-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="text-danger h-3.5 w-3.5" />
          <p className="text-danger text-xs font-semibold">Import interrompu</p>
        </div>
        <p className="text-muted-foreground mt-1 text-[11px]">{state.error}</p>
      </div>
    );
  }

  if (state.status !== 'running') return null;

  const progress = state.progress;
  const progressTotal = progress.stage === 'fit'
    ? progress.fitTotal
    : progress.stage === 'weather-recent' || progress.stage === 'weather-archive'
      ? progress.weatherTotal
      : progress.totalActivities;
  const progressDone = progress.stage === 'fit'
    ? progress.fitDone
    : progress.stage === 'weather-recent' || progress.stage === 'weather-archive'
      ? progress.weatherDone
      : undefined;
  const percent = progressTotal && progressDone != null
    ? Math.max(0, Math.min(100, Math.round((progressDone / progressTotal) * 100)))
    : null;
  const countDetail = [
    progress.totalActivities != null ? `${progress.totalActivities} activite(s)` : null,
    progress.fitPending != null ? `${progress.fitPending} FIT restant(s)` : null,
  ].filter(Boolean).join(' · ');
  const detail = [progress.detail, countDetail].filter(Boolean).join(' · ');

  return (
    <div className="border-border-subtle bg-surface-2 rounded-md border px-3 py-2">
      <div className="flex items-center gap-2">
        <RefreshCw className="text-brand-cyan h-3.5 w-3.5 animate-spin" />
        <p className="text-foreground text-xs font-semibold">{progress.label}</p>
      </div>
      {detail ? (
        <p className="text-muted-foreground mt-1 text-[11px]">{detail}</p>
      ) : null}
      {percent != null ? (
        <div className="bg-muted mt-2 h-1.5 overflow-hidden rounded-full">
          <div
            className="bg-brand-cyan h-full rounded-full transition-all"
            style={{ width: `${percent}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

interface SettingsRowProps {
  label: string;
  hint?: string;
  right?: React.ReactNode;
  isLast?: boolean;
  danger?: boolean;
  onClick?: () => void;
}

function SettingsRow({
  label,
  hint,
  right,
  isLast = false,
  danger = false,
  onClick,
}: SettingsRowProps) {
  const baseClass = cn(
    'flex w-full items-center gap-3 px-4 py-3 text-left transition',
    !isLast && 'border-border-subtle border-b',
    onClick && 'hover:bg-white/5 cursor-pointer',
  );

  const content = (
    <>
      <div className="flex-1">
        <p
          className={cn(
            'text-sm font-medium',
            danger ? 'text-danger' : 'text-foreground',
          )}
        >
          {label}
        </p>
        {hint ? (
          <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
            {hint}
          </p>
        ) : null}
      </div>
      {right}
      {onClick && !right ? <ChevronRight /> : null}
    </>
  );

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={baseClass}>
        {content}
      </button>
    );
  }
  return <div className={baseClass}>{content}</div>;
}

interface ToggleProps {
  on: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
}

function Toggle({ on, onChange, disabled = false }: ToggleProps) {
  // Layout `inline-flex items-center` : la thumb est centrée verticalement
  // sans avoir à hardcoder un `top` en absolu. La translation passe de
  // 0 (OFF) à `translate-x-5` (= 20 px = w-11 - p-0.5*2 - thumb w-5),
  // sans le décalage off-by-2 du précédent `translate-x-[18px]`.
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => !disabled && onChange(!on)}
      disabled={disabled}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full p-0.5 transition-colors',
        on ? 'bg-brand-primary' : 'bg-muted',
        disabled && 'opacity-50',
      )}
    >
      <span
        className={cn(
          'inline-block h-5 w-5 rounded-full bg-white shadow-sm transition-transform',
          on ? 'translate-x-5' : 'translate-x-0',
        )}
      />
    </button>
  );
}

function ChevronRight() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-muted-foreground"
      aria-hidden="true"
    >
      <path d="M9 6l6 6-6 6" />
    </svg>
  );
}

function formatTimeShort(time: string): string {
  // Time in PG comes as 'HH:MM:SS' — keep first 5 chars.
  return time.slice(0, 5);
}
