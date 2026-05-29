import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  ChevronDown,
  Clock,
  CloudSun,
  FileText,
  FileUp,
  Flag,
  Gauge,
  Info,
  Layers3,
  Loader2,
  MapPinned,
  Mountain,
  Plus,
  Save,
  SlidersHorizontal,
  Thermometer,
  Timer,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { AppShell } from '@/components/shared/AppShell';
import { AttachmentViewerModal } from '@/components/race/AttachmentViewerModal';
import {
  activityDisplayId,
  agonApi,
  oneYearAgoIsoDate,
  type GpxAttachmentRead,
  type GpxRouteDetail,
  type GpxRouteSummary,
  type RacePredictionResult,
  type RaceReferenceCandidate,
  type RouteRavitoPoint,
  type SavedRacePrediction,
} from '@/lib/api/agon';

type Engine = 'v1' | 'v2' | 'v3';
type ViewMode = 'predict' | 'analytics' | 'pacing';
type AnalysisMode = 'auto' | 'route' | 'trail';
type EffortMode = 'endurance' | 'steady' | 'aggressive';
type RavitoMode = 'auto' | 'manual';
type WeatherMode = 'auto' | 'manual';

const ENGINE_LABELS: Record<Engine, string> = {
  v1: 'V1 RF',
  v2: 'V2 physique',
  v3: 'V3 hybride',
};

const ENGINE_HELP: Record<Engine, string> = {
  v1: 'Ancien modele RandomForest. Utile comme baseline.',
  v2: 'Moteur physique Minetti + calibration Garmin.',
  v3: 'Choix par defaut : V2 robuste + signal historique pondere.',
};

type CoursePacingPoint = {
  name: string;
  km: number;
  elevationGainM: number;
  altitudeM: number;
  elevationLossM: number;
  bestTime: string;
  lastTime: string;
  cutoffLabel?: string;
  cutoffElapsedMin?: number;
  pauseMin?: number;
  service: 'start' | 'food' | 'hot_food' | 'drink' | 'none' | 'finish';
  baseLife?: boolean;
  personalBag?: boolean;
};

type CoursePacingRow = CoursePacingPoint & {
  predictedElapsedMin: number;
  predictedClock: string;
  isLate: boolean;
  cutoffDeltaMin: number | null;
  segmentGainM: number;
  segmentLossM: number;
  temperatureC: number | null;
  heatPenaltyPct: number;
};

type PacingStartClock = {
  date: Date | null;
  minutesOfDay: number;
};

const SWISS_CANYON_111K_POINTS: CoursePacingPoint[] = [
  {
    name: 'START',
    km: 0,
    elevationGainM: 0,
    altitudeM: 730,
    elevationLossM: 0,
    bestTime: '05:00',
    lastTime: '',
    service: 'start',
  },
  {
    name: 'Noiraigue',
    km: 12.2,
    elevationGainM: 318,
    altitudeM: 726,
    elevationLossM: 321,
    bestTime: '05:45',
    lastTime: '07:00',
    cutoffElapsedMin: 120,
    service: 'food',
  },
  {
    name: 'Le Soliat',
    km: 16.6,
    elevationGainM: 994,
    altitudeM: 1405,
    elevationLossM: 321,
    bestTime: '06:30',
    lastTime: '09:00',
    cutoffElapsedMin: 240,
    service: 'none',
  },
  {
    name: 'Petites Fauconieres',
    km: 20,
    elevationGainM: 1065,
    altitudeM: 1065,
    elevationLossM: 458,
    bestTime: '06:45',
    lastTime: '09:45',
    cutoffElapsedMin: 285,
    service: 'food',
  },
  {
    name: 'Vers Chez Pillot',
    km: 26.3,
    elevationGainM: 1078,
    altitudeM: 1106,
    elevationLossM: 702,
    bestTime: '07:05',
    lastTime: '10:30',
    cutoffElapsedMin: 330,
    service: 'none',
  },
  {
    name: 'Carriere de Motiers',
    km: 30.2,
    elevationGainM: 1087,
    altitudeM: 755,
    elevationLossM: 1063,
    bestTime: '07:30',
    lastTime: '11:00',
    cutoffElapsedMin: 360,
    service: 'food',
  },
  {
    name: 'Chasseron',
    km: 40.4,
    elevationGainM: 1986,
    altitudeM: 1603,
    elevationLossM: 1114,
    bestTime: '08:15',
    lastTime: '13:30',
    cutoffLabel: 'STOP 13:30',
    cutoffElapsedMin: 510,
    service: 'food',
  },
  {
    name: 'Vuiteboeuf',
    km: 46.9,
    elevationGainM: 1996,
    altitudeM: 602,
    elevationLossM: 2125,
    bestTime: '09:00',
    lastTime: '15:00',
    cutoffElapsedMin: 600,
    service: 'food',
  },
  {
    name: "Col de l'Aiguillon",
    km: 56.5,
    elevationGainM: 3002,
    altitudeM: 1320,
    elevationLossM: 2413,
    bestTime: '10:15',
    lastTime: '17:15',
    cutoffElapsedMin: 735,
    service: 'food',
  },
  {
    name: 'Col des Etroits',
    km: 62.6,
    elevationGainM: 3076,
    altitudeM: 1151,
    elevationLossM: 2654,
    bestTime: '11:00',
    lastTime: '18:00',
    cutoffLabel: 'STOP 18:00',
    cutoffElapsedMin: 780,
    service: 'food',
  },
  {
    name: 'Gorges de Noirveau',
    km: 73.7,
    elevationGainM: 3631,
    altitudeM: 1000,
    elevationLossM: 3364,
    bestTime: '12:15',
    lastTime: '21:30',
    cutoffLabel: 'STOP 21:30',
    cutoffElapsedMin: 990,
    service: 'hot_food',
    personalBag: true,
  },
  {
    name: 'Les Places',
    km: 82.7,
    elevationGainM: 3884,
    altitudeM: 1107,
    elevationLossM: 3508,
    bestTime: '12:45',
    lastTime: '01:00',
    cutoffElapsedMin: 1200,
    service: 'hot_food',
    baseLife: true,
  },
  {
    name: 'Les Verrieres',
    km: 88.4,
    elevationGainM: 4032,
    altitudeM: 978,
    elevationLossM: 3784,
    bestTime: '13:15',
    lastTime: '02:00',
    cutoffElapsedMin: 1260,
    service: 'drink',
  },
  {
    name: 'Bas du Chapeau de Napoleon',
    km: 95.8,
    elevationGainM: 4327,
    altitudeM: 970,
    elevationLossM: 4087,
    bestTime: '14:00',
    lastTime: '02:45',
    cutoffLabel: 'STOP 02:45',
    cutoffElapsedMin: 1305,
    service: 'hot_food',
    baseLife: true,
  },
  {
    name: 'Signal',
    km: 103.4,
    elevationGainM: 4709,
    altitudeM: 1061,
    elevationLossM: 4378,
    bestTime: '14:30',
    lastTime: '06:00',
    cutoffElapsedMin: 1500,
    service: 'none',
  },
  {
    name: 'La Roche',
    km: 108.7,
    elevationGainM: 4990,
    altitudeM: 1051,
    elevationLossM: 4668,
    bestTime: '15:15',
    lastTime: '08:00',
    cutoffElapsedMin: 1620,
    service: 'food',
    baseLife: true,
  },
  {
    name: 'FINISH',
    km: 113.1,
    elevationGainM: 5006,
    altitudeM: 730,
    elevationLossM: 5006,
    bestTime: '15:30',
    lastTime: '09:00',
    cutoffLabel: 'STOP RACE 09:00',
    cutoffElapsedMin: 1680,
    service: 'finish',
  },
];

export default function RacePredictorRoute() {
  return (
    <AppShell>
      <PredictorContent />
    </AppShell>
  );
}

export function PredictorContent() {
  const [view, setView] = useState<ViewMode>('predict');

  return (
      <div className="mx-auto w-full max-w-md px-4 pb-8 pt-4">
        <header className="mb-4">
          <p className="text-eyebrow mb-2">Race Predictor</p>
          <h1 className="font-display text-2xl font-bold tracking-tight text-foreground">
            Prediction GPX
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            V3 est le moteur par defaut. V1/V2 restent disponibles pour comparer.
          </p>
        </header>

        <div className="mb-4 grid grid-cols-3 gap-1 rounded-md border border-border-subtle bg-card p-1">
          {(
            [
              { key: 'predict', label: 'Predire', disabled: false },
              { key: 'pacing', label: 'Pacing', disabled: false },
              { key: 'analytics', label: 'Analytics', disabled: true },
            ] as Array<{ key: ViewMode; label: string; disabled: boolean }>
          ).map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                if (!item.disabled) setView(item.key);
              }}
              disabled={item.disabled}
              className={`rounded px-3 py-2 text-xs font-semibold transition ${
                view === item.key
                  ? 'bg-brand-primary text-white'
                  : item.disabled
                    ? 'text-muted-foreground/50 cursor-not-allowed'
                    : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <span className="block">{item.label}</span>
              {item.disabled ? (
                <span className="block text-[9px] font-medium uppercase tracking-wide">
                  soon
                </span>
              ) : null}
            </button>
          ))}
        </div>

        {view === 'analytics' ? (
          <PredictionAnalyticsMobile />
        ) : view === 'pacing' ? (
          <PacingMobile />
        ) : (
          <PredictionWorkspace />
        )}
      </div>
  );
}

function PredictionWorkspace() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [engine, setEngine] = useState<Engine>('v3');
  const [selectedRouteId, setSelectedRouteId] = useState<string>('');
  const [prediction, setPrediction] = useState<RacePredictionResult | null>(null);
  const [historyStartDate, setHistoryStartDate] = useState(oneYearAgoIsoDate());
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode>('auto');
  const [effortMode, setEffortMode] = useState<EffortMode>('steady');
  const [ravitoMode, setRavitoMode] = useState<RavitoMode>('auto');
  const [weatherMode, setWeatherMode] = useState<WeatherMode>('auto');
  const [temperatureC, setTemperatureC] = useState(12);
  const [raceDatetime, setRaceDatetime] = useState('');
  const [customRavitos, setCustomRavitos] = useState<RouteRavitoPoint[]>([]);
  const [name, setName] = useState('');
  const [showAttachments, setShowAttachments] = useState(false);
  const [activeAttachment, setActiveAttachment] = useState<GpxAttachmentRead | null>(
    null,
  );
  const [settingsAppliedRouteId, setSettingsAppliedRouteId] = useState<string>('');
  const [controlsOpen, setControlsOpen] = useState(true);

  const routesQuery = useQuery({
    queryKey: ['agon', 'gpx-routes'],
    queryFn: () => agonApi.listGpxRoutes(),
    staleTime: 60_000,
  });

  const routeDetailQuery = useQuery({
    queryKey: ['agon', 'gpx-route', selectedRouteId],
    queryFn: () => agonApi.getGpxRoute(selectedRouteId),
    enabled: Boolean(selectedRouteId),
    staleTime: 60_000,
  });

  const routeSettingsQuery = useQuery({
    queryKey: ['agon', 'gpx-route-settings', selectedRouteId],
    queryFn: () => agonApi.getGpxRouteSettings(selectedRouteId),
    enabled: Boolean(selectedRouteId),
    staleTime: 20_000,
  });

  const routeDetail = routeDetailQuery.data ?? null;
  const routeDistance = Number(routeDetail?.distance_km ?? 0);
  const officialCoursePlan = useMemo(
    () => coursePlanForRoute(routeDetail),
    [routeDetail],
  );
  const officialRavitos = useMemo(
    () => officialRavitosFromCoursePlan(officialCoursePlan),
    [officialCoursePlan],
  );
  const effectiveRavitos = useMemo(
    () =>
      officialRavitos.length
        ? mergeOfficialRavitos(officialRavitos, customRavitos)
        : customRavitos,
    [customRavitos, officialRavitos],
  );

  useEffect(() => {
    const settings = routeSettingsQuery.data;
    if (!settings || !selectedRouteId || settingsAppliedRouteId === selectedRouteId)
      return;
    const settingsRavitos = normalizeRavitos(settings.custom_ravitos);
    const timer = window.setTimeout(() => {
      setEngine(toEngine(settings.preferred_engine));
      setAnalysisMode(toAnalysisMode(settings.analysis_mode));
      setEffortMode(toEffortMode(settings.effort_mode));
      setRavitoMode(toRavitoMode(settings.ravito_mode));
      setWeatherMode(toWeatherMode(settings.weather_mode));
      setTemperatureC(Number(settings.manual_temperature_c ?? 12));
      setHistoryStartDate(settings.history_start_date || oneYearAgoIsoDate());
      setRaceDatetime(toDatetimeLocal(settings.race_datetime));
      setCustomRavitos(
        officialRavitos.length
          ? mergeOfficialRavitos(officialRavitos, settingsRavitos)
          : settingsRavitos,
      );
      setSettingsAppliedRouteId(selectedRouteId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [officialRavitos, routeSettingsQuery.data, selectedRouteId, settingsAppliedRouteId]);

  useEffect(() => {
    if (
      !selectedRouteId ||
      settingsAppliedRouteId !== selectedRouteId ||
      officialRavitos.length === 0
    )
      return;
    const timer = window.setTimeout(() => {
      setCustomRavitos((current) => mergeOfficialRavitos(officialRavitos, current));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [officialRavitos, selectedRouteId, settingsAppliedRouteId]);

  const saveSettingsMutation = useMutation({
    mutationFn: (routeId: string) =>
      agonApi.updateGpxRouteSettings(routeId, {
        preferred_engine: engine,
        analysis_mode: analysisMode,
        effort_mode: effortMode,
        ravito_mode: ravitoMode,
        weather_mode: weatherMode,
        manual_temperature_c: weatherMode === 'manual' ? temperatureC : null,
        history_start_date: historyStartDate,
        race_datetime: serializeDatetimeLocal(raceDatetime),
        custom_ravitos: effectiveRavitos,
      }),
  });
  const saveSettings = saveSettingsMutation.mutate;

  useEffect(() => {
    if (!selectedRouteId || settingsAppliedRouteId !== selectedRouteId) return;
    const timer = window.setTimeout(() => {
      saveSettings(selectedRouteId);
    }, 800);
    return () => window.clearTimeout(timer);
  }, [
    selectedRouteId,
    settingsAppliedRouteId,
    engine,
    analysisMode,
    effortMode,
    ravitoMode,
    weatherMode,
    temperatureC,
    historyStartDate,
    raceDatetime,
    effectiveRavitos,
    saveSettings,
  ]);

  const uploadMutation = useMutation({
    mutationFn: (file: File) => agonApi.uploadGpxRoute(file),
    onSuccess: (route) => {
      toast.success(`Trace "${route.name}" importee`);
      setSelectedRouteId(route.id);
      setPrediction(null);
      setControlsOpen(true);
      setSettingsAppliedRouteId('');
      setRavitoMode('auto');
      setCustomRavitos([]);
      void queryClient.invalidateQueries({ queryKey: ['agon', 'gpx-routes'] });
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Import impossible'),
  });

  const deleteRouteMutation = useMutation({
    mutationFn: (id: string) => agonApi.deleteGpxRoute(id),
    onSuccess: () => {
      toast.success('Trace supprimee');
      setSelectedRouteId('');
      setPrediction(null);
      setControlsOpen(true);
      setSettingsAppliedRouteId('');
      void queryClient.invalidateQueries({ queryKey: ['agon', 'gpx-routes'] });
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Suppression impossible'),
  });

  const predictMutation = useMutation({
    mutationFn: async () => {
      if (!selectedRouteId) throw new Error('Choisis une trace GPX.');
      await saveSettingsMutation.mutateAsync(selectedRouteId);
      const form = new FormData();
      form.append('route_id', selectedRouteId);
      form.append('history_start_date', historyStartDate);
      form.append('analysis_mode', analysisMode);
      form.append('ravito_mode', ravitoMode);
      form.append('effort_mode', effortMode);
      form.append('weather_mode', weatherMode);
      if (effectiveRavitos.length > 0) {
        form.append('custom_ravitos', JSON.stringify(effectiveRavitos));
      }
      if (weatherMode === 'manual') form.append('temperature_c', String(temperatureC));
      const serializedRaceDatetime = serializeDatetimeLocal(raceDatetime);
      if (serializedRaceDatetime) form.append('race_datetime', serializedRaceDatetime);
      return agonApi.predictGpx(engine, form);
    },
    onSuccess: (result) => {
      const predictionWithLocalStart = raceDatetime
        ? { ...result, race_datetime_local: serializeDatetimeLocal(raceDatetime) }
        : result;
      setPrediction(predictionWithLocalStart);
      setControlsOpen(false);
      setName(
        `${predictionWithLocalStart.filename ?? routeDetailQuery.data?.name ?? 'Prediction'} · ${ENGINE_LABELS[engine]}`,
      );
      const returnedRavitos = normalizeRavitos(
        (result.custom_ravitos as RouteRavitoPoint[] | undefined) ??
          (result.ravito_config as RouteRavitoPoint[] | undefined) ??
          [],
      );
      if (
        (ravitoMode === 'manual' || officialRavitos.length > 0) &&
        returnedRavitos.length > 0
      ) {
        setCustomRavitos(
          officialRavitos.length
            ? mergeOfficialRavitos(officialRavitos, returnedRavitos)
            : returnedRavitos,
        );
      }
      toast.success('Prediction calculee');
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Prediction impossible'),
  });

  const savePredictionMutation = useMutation({
    mutationFn: async () => {
      if (!prediction) throw new Error('Aucune prediction a sauvegarder.');
      return agonApi.saveRacePrediction({
        name:
          name.trim() ||
          `${prediction.filename ?? 'Prediction'} · ${ENGINE_LABELS[engine]}`,
        prediction,
        history_start_date: historyStartDate,
      });
    },
    onSuccess: () => {
      toast.success('Prediction sauvegardee');
      void queryClient.invalidateQueries({ queryKey: ['agon', 'race-predictions'] });
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Sauvegarde impossible'),
  });

  const handleFileImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    uploadMutation.mutate(file);
  };

  return (
    <div className="space-y-4">
      <RouteSelector
        engine={engine}
        setEngine={(value) => {
          setEngine(value);
          setControlsOpen(true);
        }}
        routes={routesQuery.data ?? []}
        loading={routesQuery.isLoading}
        selectedRouteId={selectedRouteId}
        onSelectRoute={(id) => {
          setSelectedRouteId(id);
          setSettingsAppliedRouteId('');
          setPrediction(null);
          setControlsOpen(true);
          setRavitoMode('auto');
          setCustomRavitos([]);
        }}
        onImportClick={() => fileInputRef.current?.click()}
        isImporting={uploadMutation.isPending}
      />

      <input
        ref={fileInputRef}
        type="file"
        accept=".gpx,application/gpx+xml"
        hidden
        onChange={handleFileImport}
      />

      {prediction ? (
        <PredictionResult
          prediction={prediction}
          name={name}
          onNameChange={setName}
          onSave={() => savePredictionMutation.mutate()}
          saving={savePredictionMutation.isPending}
        />
      ) : null}

      {prediction && !controlsOpen ? (
        <button
          type="button"
          onClick={() => setControlsOpen(true)}
          className="flex w-full items-center justify-between rounded-md border border-border-subtle bg-card px-4 py-3 text-left"
        >
          <span className="min-w-0">
            <span className="block text-xs font-semibold text-foreground">
              Modifier la simulation
            </span>
            <span className="block truncate text-[11px] text-muted-foreground">
              {routeDetail?.name ?? prediction.filename ?? 'Trace'} ·{' '}
              {ENGINE_LABELS[engine]} · {effortMode}
            </span>
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        </button>
      ) : null}

      {!prediction || controlsOpen ? (
        <>
          {routeDetail ? (
            <RouteSummary
              route={routeDetail}
              onShowAttachments={() => setShowAttachments(true)}
              {...(routeDetail.owned_by_user
                ? {
                    onDelete: () => {
                      if (window.confirm('Supprimer cette trace importee ?')) {
                        deleteRouteMutation.mutate(routeDetail.id);
                      }
                    },
                  }
                : {})}
              deleting={deleteRouteMutation.isPending}
            />
          ) : null}

          <ParametersSection
            analysisMode={analysisMode}
            effortMode={effortMode}
            weatherMode={weatherMode}
            temperatureC={temperatureC}
            historyStartDate={historyStartDate}
            raceDatetime={raceDatetime}
            setAnalysisMode={setAnalysisMode}
            setEffortMode={setEffortMode}
            setWeatherMode={setWeatherMode}
            setTemperatureC={setTemperatureC}
            setHistoryStartDate={setHistoryStartDate}
            setRaceDatetime={setRaceDatetime}
          />

          <RavitoPlanner
            mode={ravitoMode}
            setMode={setRavitoMode}
            ravitos={effectiveRavitos}
            setRavitos={setCustomRavitos}
            routeDistanceKm={routeDistance}
            officialRavitos={officialRavitos}
            saving={saveSettingsMutation.isPending}
          />

          <button
            type="button"
            onClick={() => predictMutation.mutate()}
            disabled={
              !selectedRouteId ||
              predictMutation.isPending ||
              routeSettingsQuery.isLoading
            }
            className="btn-glass-primary w-full"
          >
            <Gauge className="h-4 w-4" />
            {predictMutation.isPending
              ? 'Calcul...'
              : prediction
                ? `Relancer ${ENGINE_LABELS[engine]}`
                : `Lancer ${ENGINE_LABELS[engine]}`}
          </button>

          {!selectedRouteId ? (
            <p className="text-center text-[11px] text-muted-foreground">
              Choisis une trace GPX pour lancer une prediction.
            </p>
          ) : null}
        </>
      ) : null}

      {showAttachments && routeDetail ? (
        <AttachmentsModal
          route={routeDetail}
          onClose={() => setShowAttachments(false)}
          onOpen={(att) => {
            setShowAttachments(false);
            setActiveAttachment(att);
          }}
        />
      ) : null}

      {activeAttachment && routeDetail ? (
        <AttachmentViewerModal
          routeId={routeDetail.id}
          attachment={activeAttachment}
          onClose={() => setActiveAttachment(null)}
        />
      ) : null}
    </div>
  );
}

function RouteSelector({
  engine,
  setEngine,
  routes,
  loading,
  selectedRouteId,
  onSelectRoute,
  onImportClick,
  isImporting,
}: {
  engine: Engine;
  setEngine: (value: Engine) => void;
  routes: GpxRouteSummary[];
  loading: boolean;
  selectedRouteId: string;
  onSelectRoute: (id: string) => void;
  onImportClick: () => void;
  isImporting: boolean;
}) {
  const [engineOpen, setEngineOpen] = useState(false);

  return (
    <section className="rounded-md border border-border-subtle bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <FileUp className="h-5 w-5 text-brand-cyan" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-foreground">Trace de course</p>
          <p className="text-xs text-muted-foreground">
            {ENGINE_LABELS[engine]} · historique Garmin 1 an par defaut
          </p>
        </div>
      </div>

      <div className="mb-2 grid grid-cols-[1fr_auto] items-end gap-2">
        <label className="min-w-0">
          <span className="mb-1 block text-xs text-muted-foreground">GPX disponible</span>
          <select
            value={selectedRouteId}
            onChange={(event) => onSelectRoute(event.target.value)}
            disabled={loading || isImporting}
            className="bg-surface-2 w-full rounded-md border border-border-subtle px-3 py-2 text-sm"
          >
            <option value="">{loading ? 'Chargement...' : 'Choisir une trace'}</option>
            {routes.map((route) => (
              <option key={route.id} value={route.id}>
                {routeOptionLabel(route)}
              </option>
            ))}
          </select>
        </label>

        <div className="relative">
          <span className="mb-1 block text-xs text-muted-foreground">Moteur</span>
          <button
            type="button"
            onClick={() => setEngineOpen((value) => !value)}
            className="bg-surface-2 flex h-10 items-center gap-1.5 rounded-md border border-border-subtle px-3 text-xs font-semibold text-foreground"
            aria-label="Choisir le moteur de prediction"
          >
            <Layers3 className="h-3.5 w-3.5 text-brand-cyan" />
            {engine.toUpperCase()}
          </button>
          {engineOpen ? (
            <div className="absolute right-0 z-20 mt-2 w-56 rounded-md border border-border-subtle bg-card p-2 shadow-xl">
              {(['v3', 'v2', 'v1'] as Engine[]).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    setEngine(item);
                    setEngineOpen(false);
                  }}
                  className={`mb-1 w-full rounded-md px-3 py-2 text-left last:mb-0 ${
                    engine === item
                      ? 'bg-brand-primary/15 text-foreground'
                      : 'hover:bg-surface-2 text-muted-foreground'
                  }`}
                >
                  <span className="block text-xs font-semibold">
                    {ENGINE_LABELS[item]}
                  </span>
                  <span className="block text-[10px] leading-snug">
                    {ENGINE_HELP[item]}
                  </span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <button
        type="button"
        onClick={onImportClick}
        disabled={isImporting}
        className="inline-flex items-center gap-1 text-xs font-semibold text-brand-cyan hover:text-foreground disabled:opacity-50"
      >
        {isImporting ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Import en cours...
          </>
        ) : (
          <>
            <Upload className="h-3.5 w-3.5" /> Importer un GPX
          </>
        )}
      </button>
    </section>
  );
}

function RouteSummary({
  route,
  onShowAttachments,
  onDelete,
  deleting,
}: {
  route: GpxRouteDetail;
  onShowAttachments: () => void;
  onDelete?: () => void;
  deleting: boolean;
}) {
  const distance =
    route.distance_km != null ? `${route.distance_km.toFixed(1)} km` : '--';
  const elevation =
    route.elevation_gain_m != null ? `+${Math.round(route.elevation_gain_m)} m` : '--';
  const attachmentCount = route.attachments.length;

  return (
    <section className="rounded-md border border-border-subtle bg-card p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">{route.name}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {distance} · {elevation} · {route.is_public ? 'Catalogue' : 'Import perso'}
          </p>
        </div>
        {onDelete ? (
          <button
            type="button"
            onClick={onDelete}
            disabled={deleting}
            className="rounded-md p-1.5 text-muted-foreground hover:text-danger disabled:opacity-50"
            aria-label="Supprimer la trace"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        ) : null}
      </div>

      {attachmentCount > 0 ? (
        <button
          type="button"
          onClick={onShowAttachments}
          className="border-brand-primary/40 bg-brand-primary/10 hover:bg-brand-primary/20 relative inline-flex items-center gap-2 rounded-md border px-3 py-2 text-xs font-semibold text-foreground transition"
        >
          <Info className="h-4 w-4 text-brand-primary" />
          Infos complementaires
          <span className="ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-primary px-1.5 text-[11px] text-foreground">
            {attachmentCount}
          </span>
        </button>
      ) : null}
    </section>
  );
}

function ParametersSection({
  analysisMode,
  effortMode,
  weatherMode,
  temperatureC,
  historyStartDate,
  raceDatetime,
  setAnalysisMode,
  setEffortMode,
  setWeatherMode,
  setTemperatureC,
  setHistoryStartDate,
  setRaceDatetime,
}: {
  analysisMode: AnalysisMode;
  effortMode: EffortMode;
  weatherMode: WeatherMode;
  temperatureC: number;
  historyStartDate: string;
  raceDatetime: string;
  setAnalysisMode: (value: AnalysisMode) => void;
  setEffortMode: (value: EffortMode) => void;
  setWeatherMode: (value: WeatherMode) => void;
  setTemperatureC: (value: number) => void;
  setHistoryStartDate: (value: string) => void;
  setRaceDatetime: (value: string) => void;
}) {
  return (
    <section className="rounded-md border border-border-subtle bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <SlidersHorizontal className="h-4 w-4 text-brand-cyan" />
        <p className="text-sm font-semibold text-foreground">Parametres de prediction</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <MobileSelect
          label="Terrain"
          value={analysisMode}
          onChange={(value) => setAnalysisMode(value as AnalysisMode)}
          options={[
            ['auto', 'Auto'],
            ['route', 'Route'],
            ['trail', 'Trail'],
          ]}
        />
        <MobileSelect
          label="Effort"
          value={effortMode}
          onChange={(value) => setEffortMode(value as EffortMode)}
          options={[
            ['endurance', 'Endurance'],
            ['steady', 'Maitrise'],
            ['aggressive', 'Agressif'],
          ]}
        />
        <MobileSelect
          label="Meteo"
          value={weatherMode}
          onChange={(value) => setWeatherMode(value as WeatherMode)}
          options={[
            ['auto', 'Auto'],
            ['manual', 'Manuelle'],
          ]}
        />
        {weatherMode === 'manual' ? (
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Temperature</span>
            <input
              type="number"
              value={temperatureC}
              onChange={(event) => setTemperatureC(Number(event.target.value))}
              className="bg-surface-2 w-full rounded-md border border-border-subtle px-3 py-2 text-sm"
            />
          </label>
        ) : (
          <div className="bg-surface-2 rounded-md border border-border-subtle p-3">
            <CloudSun className="mb-1 h-4 w-4 text-brand-cyan" />
            <p className="text-[11px] text-muted-foreground">
              Meteo auto par segment si disponible.
            </p>
          </div>
        )}
        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">Historique</span>
          <input
            type="date"
            value={historyStartDate}
            onChange={(event) => setHistoryStartDate(event.target.value)}
            className="bg-surface-2 w-full rounded-md border border-border-subtle px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs text-muted-foreground">Depart</span>
          <input
            type="datetime-local"
            value={raceDatetime}
            onChange={(event) => setRaceDatetime(event.target.value)}
            className="bg-surface-2 w-full rounded-md border border-border-subtle px-3 py-2 text-sm"
          />
        </label>
      </div>
    </section>
  );
}

function RavitoPlanner({
  mode,
  setMode,
  ravitos,
  setRavitos,
  routeDistanceKm,
  officialRavitos,
  saving,
}: {
  mode: RavitoMode;
  setMode: (value: RavitoMode) => void;
  ravitos: RouteRavitoPoint[];
  setRavitos: (value: RouteRavitoPoint[]) => void;
  routeDistanceKm: number;
  officialRavitos: RouteRavitoPoint[];
  saving: boolean;
}) {
  const hasOfficialRavitos = officialRavitos.length > 0;
  const displayedRavitos = hasOfficialRavitos
    ? mergeOfficialRavitos(officialRavitos, ravitos)
    : ravitos;

  const handleModeChange = (value: string) => {
    const nextMode = value as RavitoMode;
    if (hasOfficialRavitos) {
      setRavitos(displayedRavitos);
    }
    setMode(nextMode);
  };

  const addRavito = () => {
    const lastKm = ravitos.length ? Number(ravitos[ravitos.length - 1]?.km ?? 0) : 0;
    const nextKm =
      routeDistanceKm > 0
        ? Math.min(routeDistanceKm - 0.5, Math.max(1, lastKm + 10))
        : Math.max(1, lastKm + 10);
    setMode('manual');
    setRavitos([
      ...ravitos,
      { km: roundOne(nextKm), name: `Ravito ${ravitos.length + 1}`, pause_min: 3 },
    ]);
  };

  const updateRavito = (index: number, patch: Partial<RouteRavitoPoint>) => {
    setRavitos(
      displayedRavitos.map((ravito, ravitoIndex) =>
        ravitoIndex === index ? { ...ravito, ...patch } : ravito,
      ),
    );
  };

  const removeRavito = (index: number) => {
    setRavitos(displayedRavitos.filter((_, ravitoIndex) => ravitoIndex !== index));
  };

  return (
    <section className="rounded-md border border-border-subtle bg-card p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Clock className="h-4 w-4 text-brand-cyan" />
          <div>
            <p className="text-sm font-semibold text-foreground">Ravitos</p>
            <p className="text-xs text-muted-foreground">
              {saving ? 'Sauvegarde...' : 'Sauvegarde automatique par GPX'}
            </p>
          </div>
        </div>
        <MobileSelect
          label=""
          value={mode}
          onChange={handleModeChange}
          compact
          options={[
            ['auto', 'Auto'],
            ['manual', 'Manuel'],
          ]}
        />
      </div>

      {hasOfficialRavitos ? (
        <div className="space-y-3">
          <div className="border-brand-cyan/25 bg-brand-cyan/10 rounded-md border p-3 text-xs text-muted-foreground">
            {mode === 'auto'
              ? 'Auto utilise les ravitos officiels connus de cette trace. Les noms et distances restent fixes.'
              : 'Manuel calibre seulement la duree des pauses. Les ravitos officiels restent verrouilles.'}
          </div>
          <div className="space-y-2">
            {displayedRavitos.map((ravito, index) => (
              <div
                key={`${ravito.name}-${ravito.km}`}
                className="bg-surface-2 rounded-md border border-border-subtle p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-foreground">
                      {ravito.name || `Ravito ${index + 1}`}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      Km {Number(ravito.km).toFixed(1)}
                    </p>
                  </div>
                  {mode === 'manual' ? (
                    <label className="w-24 shrink-0">
                      <span className="mb-1 block text-[10px] text-muted-foreground">
                        Pause min
                      </span>
                      <input
                        type="number"
                        value={ravito.pause_min}
                        min={0}
                        step={0.5}
                        onChange={(event) =>
                          updateRavito(index, { pause_min: Number(event.target.value) })
                        }
                        className="w-full rounded-md border border-border-subtle bg-card px-2 py-2 text-sm"
                      />
                    </label>
                  ) : (
                    <span className="shrink-0 rounded-full border border-border-subtle bg-card px-2 py-1 text-[11px] font-semibold text-muted-foreground">
                      {Number(ravito.pause_min).toFixed(1)} min
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
          {mode === 'auto' ? (
            <button
              type="button"
              onClick={() => handleModeChange('manual')}
              className="inline-flex items-center gap-1 text-xs font-semibold text-brand-cyan hover:text-foreground"
            >
              <SlidersHorizontal className="h-3.5 w-3.5" /> Calibrer les pauses
            </button>
          ) : null}
        </div>
      ) : mode === 'auto' ? (
        <div className="bg-surface-2 rounded-md border border-border-subtle p-3 text-xs text-muted-foreground">
          Les pauses sont estimees selon distance, D+, duree prevue et chaleur.
        </div>
      ) : (
        <div className="space-y-3">
          {displayedRavitos.map((ravito, index) => (
            <div
              key={`${ravito.name}-${index}`}
              className="bg-surface-2 rounded-md border border-border-subtle p-3"
            >
              <div className="mb-2 flex items-center justify-between">
                <p className="text-xs font-semibold text-foreground">
                  Ravito {index + 1}
                </p>
                <button
                  type="button"
                  onClick={() => removeRavito(index)}
                  className="rounded p-1 text-muted-foreground hover:text-danger"
                  aria-label="Supprimer ravito"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="grid grid-cols-[1fr_1fr] gap-2">
                <label>
                  <span className="mb-1 block text-[11px] text-muted-foreground">Km</span>
                  <input
                    type="number"
                    value={ravito.km}
                    min={0}
                    step={0.1}
                    onChange={(event) =>
                      updateRavito(index, { km: Number(event.target.value) })
                    }
                    className="w-full rounded-md border border-border-subtle bg-card px-2 py-2 text-sm"
                  />
                </label>
                <label>
                  <span className="mb-1 block text-[11px] text-muted-foreground">
                    Pause min
                  </span>
                  <input
                    type="number"
                    value={ravito.pause_min}
                    min={0}
                    step={0.5}
                    onChange={(event) =>
                      updateRavito(index, { pause_min: Number(event.target.value) })
                    }
                    className="w-full rounded-md border border-border-subtle bg-card px-2 py-2 text-sm"
                  />
                </label>
              </div>
              <label className="mt-2 block">
                <span className="mb-1 block text-[11px] text-muted-foreground">Nom</span>
                <input
                  value={ravito.name}
                  onChange={(event) => updateRavito(index, { name: event.target.value })}
                  className="w-full rounded-md border border-border-subtle bg-card px-2 py-2 text-sm"
                />
              </label>
            </div>
          ))}
          <button
            type="button"
            onClick={addRavito}
            className="inline-flex items-center gap-1 text-xs font-semibold text-brand-cyan hover:text-foreground"
          >
            <Plus className="h-3.5 w-3.5" /> Ajouter un ravito
          </button>
        </div>
      )}
      {!hasOfficialRavitos && mode === 'auto' ? (
        <button
          type="button"
          onClick={addRavito}
          className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-cyan hover:text-foreground"
        >
          <Plus className="h-3.5 w-3.5" /> Passer en manuel
        </button>
      ) : null}
    </section>
  );
}

function PredictionResult({
  prediction,
  name,
  onNameChange,
  onSave,
  saving,
  readonly = false,
}: {
  prediction: RacePredictionResult;
  name: string;
  onNameChange: (value: string) => void;
  onSave: () => void;
  saving: boolean;
  readonly?: boolean;
}) {
  const total = metric(prediction, 'total_time_min', 'summary.total_time_min');
  const moving = metric(prediction, 'moving_time_min', 'summary.moving_time_min');
  const pauses = metric(prediction, 'total_pause_min', 'summary.total_pause_min');
  const distance = metric(prediction, 'total_distance_km', 'summary.total_distance_km');
  const elevation = metric(
    prediction,
    'total_elevation_gain_m',
    'summary.total_elevation_gain_m',
  );
  const p10 = metric(
    prediction,
    'uncertainty.total_time.p10',
    'summary.p10_total_time_min',
  );
  const p50 = metric(
    prediction,
    'uncertainty.total_time.p50',
    'summary.p50_total_time_min',
    'total_time_min',
  );
  const p90 = metric(
    prediction,
    'uncertainty.total_time.p90',
    'summary.p90_total_time_min',
  );
  const coursePlan = coursePlanForPredictionResult(prediction, name);
  const pacingRows = coursePlan
    ? buildCoursePacingRows(prediction, coursePlan, pacingStartClock(prediction, coursePlan))
    : [];
  const ravitoCount = pacingRows.filter(
    (row) => isFoodRavito(row) && row.km > 0,
  ).length;

  return (
    <section className="rounded-md border border-border-subtle bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-foreground">Resultat detaille</p>
          <p className="text-xs text-muted-foreground">
            {prediction.engine_version ?? 'engine'}
          </p>
        </div>
        <span className="rounded-full bg-[var(--chip-bg)] px-2 py-1 text-[11px] text-muted-foreground">
          {prediction.analysis_mode ?? 'mode'}
        </span>
      </div>

      <div className="border-brand-primary/20 bg-brand-primary/10 rounded-md border p-4 text-center">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
          Temps de course predit
        </p>
        <p className="mt-2 text-4xl font-bold leading-none text-foreground">
          {formatMinutes(total)}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Scenario central avec ravitos et incertitude de course
        </p>
        {p10 > 0 && p90 > 0 ? (
          <PredictionUncertaintyGauge
            p10={p10}
            p50={p50 || total}
            p90={p90}
            predicted={total}
          />
        ) : null}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <ResultCard label="Moving" value={formatMinutes(moving)} />
        <ResultCard label="Pauses" value={formatMinutes(pauses)} />
        <ResultCard label="Distance" value={`${distance.toFixed(1)} km`} />
        <ResultCard label="D+" value={`${Math.round(elevation)} m`} />
      </div>

      {!readonly ? (
        <div className="mt-4 flex gap-2">
          <input
            value={name}
            onChange={(event) => onNameChange(event.target.value)}
            className="bg-surface-2 min-w-0 flex-1 rounded-md border border-border-subtle px-3 py-2 text-sm"
            placeholder="Nom de sauvegarde"
          />
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            className="rounded-md bg-brand-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
            aria-label="Enregistrer"
          >
            <Save className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      {prediction.warnings?.length ? (
        <div className="border-warning/30 mt-3 rounded-md border bg-warning-bg p-3 text-xs text-warning-fg">
          {prediction.warnings.slice(0, 2).join(' ')}
        </div>
      ) : null}

      <div className="mt-4 space-y-2">
        <DetailDisclosure
          title="Graph"
          icon={<Mountain className="h-4 w-4 text-brand-cyan" />}
        >
          {pacingRows.length ? (
            <PacingBriefingVisual
              prediction={prediction}
              rows={pacingRows}
              ravitoCount={ravitoCount}
              totalTime={total}
              embedded
            />
          ) : (
            <p className="text-xs text-muted-foreground">
              Profil de pacing indisponible pour cette prediction.
            </p>
          )}
        </DetailDisclosure>

        <DetailDisclosure
          title="Temps de passage"
          icon={<Clock className="h-4 w-4 text-brand-cyan" />}
        >
          {pacingRows.length ? (
            <PacingCheckpointCards rows={pacingRows} embedded />
          ) : (
            <p className="text-xs text-muted-foreground">Aucun passage calcule.</p>
          )}
        </DetailDisclosure>

        <DetailDisclosure
          title="Tableau complet"
          icon={<MapPinned className="h-4 w-4 text-brand-cyan" />}
        >
          {pacingRows.length ? (
            <PacingCompleteTable
              prediction={prediction}
              rows={pacingRows}
              totalTime={total}
              embedded
            />
          ) : (
            <p className="text-xs text-muted-foreground">
              Tableau de pacing indisponible pour cette prediction.
            </p>
          )}
        </DetailDisclosure>

        <DetailDisclosure
          title="Athlete, meteo et moteur"
          icon={<SlidersHorizontal className="h-4 w-4 text-brand-cyan" />}
        >
          <div className="space-y-3">
            <TechnicalSubsection title="Calibration athlete">
              <KeyValueGrid
                data={
                  prediction.calibration ??
                  prediction.athlete_model ??
                  prediction.debug_trace
                }
                keys={[
                  ['p_run_wkg', 'P run'],
                  ['p_ref_steady_wkg', 'P steady'],
                  ['calibration_quality', 'Qualite'],
                  ['sample_count', 'Samples'],
                  ['source', 'Source'],
                ]}
              />
            </TechnicalSubsection>
            <TechnicalSubsection title="Meteo et altitude">
              <KeyValueGrid
                data={prediction.environment}
                keys={[
                  ['weather_source', 'Source'],
                  ['temperature_c', 'Temp.'],
                  ['temperature_max_c', 'Max'],
                  ['weather_factor', 'Facteur'],
                  ['altitude_factor_mean', 'Altitude'],
                ]}
              />
            </TechnicalSubsection>
            <TechnicalSubsection title="Fatigue et moteur">
              <KeyValueGrid
                data={
                  prediction.fatigue ?? prediction.hybrid_model ?? prediction.debug_trace
                }
                keys={[
                  ['fatigue_alpha', 'Alpha'],
                  ['alpha', 'Alpha'],
                  ['source', 'Source'],
                  ['residual_correction_min', 'Correction'],
                  ['confidence', 'Confiance'],
                ]}
              />
            </TechnicalSubsection>
          </div>
        </DetailDisclosure>
      </div>
    </section>
  );
}

function PredictionUncertaintyGauge({
  p10,
  p50,
  p90,
  predicted,
}: {
  p10: number;
  p50: number;
  p90: number;
  predicted: number;
}) {
  const span = Math.max(1, p90 - p10);
  const markerPercent = Math.max(0, Math.min(100, ((predicted - p10) / span) * 100));
  const p50Percent = Math.max(0, Math.min(100, ((p50 - p10) / span) * 100));

  return (
    <div
      className="mt-5 text-left"
      aria-label={`Fenetre de course ${formatMinutes(p10)} a ${formatMinutes(p90)}`}
    >
      <div className="mb-2 flex items-center justify-between text-[11px] font-medium text-muted-foreground">
        <span>Favorable</span>
        <span>Attendu</span>
        <span>Prudent</span>
      </div>
      <div className="relative h-10">
        <div className="bg-surface-2 absolute left-0 right-0 top-4 h-2 overflow-hidden rounded-full shadow-inner">
          <div className="h-full rounded-full bg-gradient-to-r from-brand-cyan via-brand-primary to-warning" />
        </div>
        <div
          className="absolute top-1 h-8 w-px bg-[var(--foreground)]"
          style={{ left: `${p50Percent}%` }}
          aria-hidden="true"
        />
        <div
          className="absolute top-0 flex -translate-x-1/2 flex-col items-center"
          style={{ left: `${markerPercent}%` }}
        >
          <div className="h-4 w-4 rounded-full border-2 border-card bg-foreground shadow-lg" />
          <span className="mt-1 rounded-full bg-card px-2 py-0.5 text-[10px] font-semibold text-foreground shadow-sm">
            Prevu
          </span>
        </div>
      </div>
      <div className="mt-1 grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <p className="font-semibold text-foreground">{formatMinutes(p10)}</p>
          <p className="text-muted-foreground">P10</p>
        </div>
        <div className="text-center">
          <p className="font-semibold text-foreground">{formatMinutes(p50)}</p>
          <p className="text-muted-foreground">P50</p>
        </div>
        <div className="text-right">
          <p className="font-semibold text-foreground">{formatMinutes(p90)}</p>
          <p className="text-muted-foreground">P90</p>
        </div>
      </div>
    </div>
  );
}

function PacingMobile() {
  const queryClient = useQueryClient();
  const [predictionId, setPredictionId] = useState('');
  const predictionsQuery = useQuery({
    queryKey: ['agon', 'race-predictions'],
    queryFn: () => agonApi.getSavedRacePredictions(),
  });

  const predictions = useMemo(
    () => predictionsQuery.data?.items ?? [],
    [predictionsQuery.data?.items],
  );
  const selectedPredictionId = predictionId || predictions[0]?.id || '';
  const selectedPrediction =
    predictions.find((prediction) => prediction.id === selectedPredictionId) ?? null;
  const coursePlan = selectedPrediction
    ? coursePlanForPrediction(selectedPrediction)
    : null;
  const deletePredictionMutation = useMutation({
    mutationFn: (id: string) => agonApi.deleteSavedRacePrediction(id),
    onSuccess: () => {
      toast.success('Prediction supprimee');
      setPredictionId('');
      void queryClient.invalidateQueries({ queryKey: ['agon', 'race-predictions'] });
      void queryClient.invalidateQueries({ queryKey: ['agon', 'race-comparisons'] });
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Suppression impossible'),
  });

  const handleDeletePrediction = () => {
    if (!selectedPrediction) return;
    const confirmed = window.confirm(
      `Supprimer la prediction "${selectedPrediction.name}" ?`,
    );
    if (!confirmed) return;
    deletePredictionMutation.mutate(selectedPrediction.id);
  };

  return (
    <section className="space-y-4">
      <div className="rounded-md border border-border-subtle bg-card p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Clock className="h-5 w-5 shrink-0 text-brand-cyan" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">Pacing</p>
              <p className="text-xs text-muted-foreground">
                Charge une prediction sauvegardee pour consulter le detail de course.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDeletePrediction}
            disabled={!selectedPrediction || deletePredictionMutation.isPending}
            className="disabled:text-muted-foreground/40 rounded p-2 text-muted-foreground transition hover:text-danger"
            aria-label="Supprimer la prediction sauvegardee"
          >
            {deletePredictionMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </button>
        </div>
        <MobileSelect
          label="Prediction sauvegardee"
          value={selectedPredictionId}
          onChange={setPredictionId}
          options={[
            ['', predictionsQuery.isLoading ? 'Chargement...' : 'Choisir une prediction'],
            ...predictions.map(
              (prediction) =>
                [prediction.id, predictionLabel(prediction)] as [string, string],
            ),
          ]}
        />
      </div>

      {selectedPrediction ? (
        <>
          {coursePlan ? (
            <CoursePacingTable
              prediction={selectedPrediction.prediction_data}
              points={coursePlan}
            />
          ) : (
            <div className="rounded-md border border-border-subtle bg-card p-4">
              <p className="text-sm font-semibold text-foreground">
                Plan de course non renseigne
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Les ravitos officiels seront affiches ici quand un plan est attache a la
                trace.
              </p>
            </div>
          )}
          <PredictionResult
            prediction={selectedPrediction.prediction_data}
            name={selectedPrediction.name}
            onNameChange={() => undefined}
            onSave={() => undefined}
            saving={false}
            readonly
          />
        </>
      ) : (
        <div className="rounded-md border border-dashed border-border-subtle bg-card p-4 text-center">
          <p className="text-sm font-semibold text-foreground">
            Aucune prediction selectionnee
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Sauvegarde une prediction depuis l'onglet Predire pour preparer ton pacing.
          </p>
        </div>
      )}
    </section>
  );
}

function CoursePacingTable({
  prediction,
  points,
}: {
  prediction: RacePredictionResult;
  points: CoursePacingPoint[];
}) {
  const ravitoCount = points.filter(
    (point) => isFoodRavito(point) && point.km > 0,
  ).length;
  const startClock = pacingStartClock(prediction, points);
  const rows = buildCoursePacingRows(prediction, points, startClock);
  const totalTime = metric(prediction, 'total_time_min', 'summary.total_time_min');

  return (
    <>
      <PacingBriefingVisual
        prediction={prediction}
        rows={rows}
        ravitoCount={ravitoCount}
        totalTime={totalTime}
      />

      <PacingCheckpointCards rows={rows} />

      <PacingCompleteTable prediction={prediction} rows={rows} totalTime={totalTime} />
    </>
  );
}

function PacingBriefingVisual({
  prediction,
  rows,
  ravitoCount,
  totalTime,
  embedded = false,
}: {
  prediction: RacePredictionResult;
  rows: CoursePacingRow[];
  ravitoCount: number;
  totalTime: number;
  embedded?: boolean;
}) {
  const distance = metric(prediction, 'total_distance_km', 'summary.total_distance_km');
  const elevation = metric(
    prediction,
    'total_elevation_gain_m',
    'summary.total_elevation_gain_m',
  );
  const moving = metric(prediction, 'moving_time_min', 'summary.moving_time_min');
  const highest = rows.reduce<CoursePacingRow | null>(
    (best, row) => (!best || row.altitudeM > best.altitudeM ? row : best),
    null,
  );
  const hottest = rows.reduce<CoursePacingRow | null>((best, row) => {
    if (row.temperatureC == null) return best;
    if (!best || best.temperatureC == null || row.temperatureC > best.temperatureC)
      return row;
    return best;
  }, null);
  const tightestCutoff = rows.reduce<CoursePacingRow | null>((best, row) => {
    if (row.cutoffDeltaMin == null || row.km <= 0) return best;
    if (!best || best.cutoffDeltaMin == null) return row;
    return row.cutoffDeltaMin > best.cutoffDeltaMin ? row : best;
  }, null);

  return (
    <section
      className={
        embedded
          ? 'space-y-3'
          : 'overflow-hidden rounded-md border border-border-subtle bg-card'
      }
    >
      <div className={embedded ? '' : 'border-b border-border-subtle p-4'}>
        {!embedded ? (
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-eyebrow">Briefing pacing</p>
            <h2 className="mt-1 font-display text-xl font-bold text-foreground">
              Profil, ravitos et passage predit
            </h2>
          </div>
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--chip-bg)] px-2 py-1 text-[11px] font-semibold text-brand-cyan">
            <Flag className="h-3.5 w-3.5" />
            {formatPacingDuration(totalTime)}
          </span>
        </div>
        ) : null}

        <div className={`${embedded ? '' : 'mt-4'} grid grid-cols-3 gap-2`}>
          <BriefingMetric
            label="Distance"
            value={distance > 0 ? `${distance.toFixed(1)} km` : '--'}
          />
          <BriefingMetric
            label="D+"
            value={elevation > 0 ? `+${Math.round(elevation)} m` : '--'}
          />
          <BriefingMetric label="Ravitos" value={String(ravitoCount)} />
        </div>
      </div>

      <div className={embedded ? 'space-y-3' : 'p-4'}>
        <ElevationProfileChart rows={rows} totalDistanceKm={distance} />

        <div className="mt-3 grid grid-cols-3 gap-2">
          <BriefingInsight
            icon={<Mountain className="h-3.5 w-3.5" />}
            label="Point haut"
            value={
              highest
                ? `${highest.name} · ${Math.round(highest.altitudeM)} m`
                : '--'
            }
          />
          <BriefingInsight
            icon={<Thermometer className="h-3.5 w-3.5" />}
            label="Plus chaud"
            value={
              hottest && hottest.temperatureC != null
                ? `${Math.round(hottest.temperatureC)}°C · ${hottest.name}`
                : '--'
            }
          />
          <BriefingInsight
            icon={<Timer className="h-3.5 w-3.5" />}
            label="Barriere"
            value={
              tightestCutoff?.cutoffDeltaMin != null
                ? `${formatCutoffStatus(tightestCutoff.cutoffDeltaMin)} · ${tightestCutoff.name}`
                : 'Aucune'
            }
            tone={
              tightestCutoff?.cutoffDeltaMin != null &&
              tightestCutoff.cutoffDeltaMin > 0
                ? 'danger'
                : 'default'
            }
          />
        </div>

        <div className="mt-3 flex items-center justify-between rounded-md bg-[var(--chip-bg)] px-3 py-2 text-[11px] text-muted-foreground">
          <span>Moving {formatPacingDuration(moving)}</span>
          <span>{rows.length} points de passage</span>
        </div>
      </div>
    </section>
  );
}

function BriefingMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-surface-2 p-3">
      <p className="text-sm font-bold leading-none text-foreground">{value}</p>
      <p className="mt-1 text-[11px] text-muted-foreground">{label}</p>
    </div>
  );
}

function BriefingInsight({
  icon,
  label,
  value,
  tone = 'default',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: 'default' | 'danger';
}) {
  return (
    <div className="min-w-0 rounded-md border border-border-subtle bg-surface-2 p-2">
      <p
        className={`flex items-center gap-1 text-[10px] font-semibold ${
          tone === 'danger' ? 'text-danger' : 'text-muted-foreground'
        }`}
      >
        {icon}
        {label}
      </p>
      <p className="mt-1 line-clamp-2 text-[11px] font-semibold leading-snug text-foreground">
        {value}
      </p>
    </div>
  );
}

// Trace d'altitude dense (interpolation lissee smoothstep + micro-relief) a
// partir des checkpoints — donne une courbe realiste type GPX (style V3).
function buildElevationTrace(
  points: Array<{ km: number; altitudeM: number }>,
  totalDist: number,
  nSamples: number,
): Array<{ km: number; alt: number }> {
  const trace: Array<{ km: number; alt: number }> = [];
  const first = points[0]!;
  const last = points[points.length - 1]!;
  for (let i = 0; i <= nSamples; i += 1) {
    const km = (i / nSamples) * totalDist;
    let a = first;
    let b = last;
    for (let j = 0; j < points.length - 1; j += 1) {
      if (km >= points[j]!.km && km <= points[j + 1]!.km) {
        a = points[j]!;
        b = points[j + 1]!;
        break;
      }
    }
    const span = b.km - a.km || 1;
    const f = (km - a.km) / span;
    const smooth = f * f * (3 - 2 * f);
    const base = a.altitudeM + (b.altitudeM - a.altitudeM) * smooth;
    const noise = Math.sin(km * 1.7) * 14 + Math.sin(km * 0.6) * 22 + Math.cos(km * 3.3) * 7;
    trace.push({ km, alt: base + noise * (1 - Math.abs(0.5 - f) * 1.2) });
  }
  return trace;
}

// Couleur de la pastille timeline selon le type de point.
function pacingDotColor(service: CoursePacingPoint['service']): string {
  switch (service) {
    case 'food':
    case 'hot_food':
      return 'var(--brand-sunset)';
    case 'drink':
      return 'var(--info)';
    case 'finish':
      return 'var(--foreground)';
    case 'start':
      return 'var(--success-fg)';
    default:
      return 'var(--muted-foreground)';
  }
}

function ElevationProfileChart({
  rows,
  totalDistanceKm,
}: {
  rows: CoursePacingRow[];
  totalDistanceKm: number;
}) {
  const W = 360;
  const H = 150;
  const topPad = 26;
  const botAxis = 18;
  const profile = rows.filter(
    (row) =>
      Number.isFinite(row.km) &&
      Number.isFinite(row.altitudeM) &&
      row.km >= 0,
  );

  if (profile.length < 2) {
    return (
      <div className="rounded-md border border-dashed border-border-subtle bg-surface-2 p-4 text-xs text-muted-foreground">
        Profil altimetrique indisponible pour cette prediction.
      </div>
    );
  }

  const totalDist = Math.max(totalDistanceKm, ...profile.map((point) => point.km), 1);
  const trace = buildElevationTrace(profile, totalDist, 180);
  const alts = trace.map((point) => point.alt);
  const minAlt = Math.min(...alts);
  const maxAlt = Math.max(...alts);
  const range = Math.max(1, maxAlt - minAlt);
  const xForKm = (km: number) => (km / totalDist) * W;
  const yForAlt = (alt: number) =>
    topPad + (H - topPad - botAxis) - ((alt - minAlt) / range) * (H - topPad - botAxis);
  // altitude exacte de la trace dense pour un km donne (ravito au contact).
  const altAt = (km: number) => {
    for (let i = 0; i < trace.length - 1; i += 1) {
      const a = trace[i]!;
      const b = trace[i + 1]!;
      if (km >= a.km && km <= b.km) {
        const f = (km - a.km) / ((b.km - a.km) || 1);
        return a.alt + (b.alt - a.alt) * f;
      }
    }
    return trace[trace.length - 1]!.alt;
  };
  const linePts = trace
    .map((point) => `${xForKm(point.km).toFixed(1)},${yForAlt(point.alt).toFixed(1)}`)
    .join(' ');
  const areaPts = `0,${H - botAxis} ${linePts} ${W},${H - botAxis}`;
  const ravitos = profile.filter((row) => isOfficialAidPoint(row));
  const tickStep = totalDist > 80 ? 20 : totalDist > 40 ? 10 : 5;
  const kmTicks: number[] = [];
  for (let km = 0; km < totalDist - tickStep / 2; km += tickStep) kmTicks.push(km);
  kmTicks.push(Math.round(totalDist));

  return (
    <div className="rounded-md border border-border-subtle bg-surface-2 p-2">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Profil altimetrique avec points de ravitaillement"
        className="block w-full"
        style={{ overflow: 'visible' }}
      >
        <defs>
          <linearGradient id="pacing-elevation-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--brand-sunset)" stopOpacity="0.34" />
            <stop offset="100%" stopColor="var(--brand-sunset)" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {/* grilles horizontales */}
        {[0.33, 0.66].map((f) => {
          const gy = topPad + f * (H - topPad - botAxis);
          return <line key={f} x1={0} x2={W} y1={gy} y2={gy} stroke="var(--border-subtle)" />;
        })}

        {/* trace exacte du parcours */}
        <polygon points={areaPts} fill="url(#pacing-elevation-fill)" />
        <polyline
          points={linePts}
          fill="none"
          stroke="var(--brand-sunset)"
          strokeWidth="1.8"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* axe des km */}
        <line x1={0} x2={W} y1={H - botAxis} y2={H - botAxis} stroke="var(--border-subtle)" />
        {kmTicks.map((km, index) => (
          <g key={`tick-${km}`}>
            <line
              x1={xForKm(km)}
              x2={xForKm(km)}
              y1={H - botAxis}
              y2={H - botAxis + 3}
              stroke="var(--muted-foreground)"
              strokeOpacity={0.5}
            />
            <text
              x={xForKm(km)}
              y={H - 5}
              fill="var(--muted-foreground)"
              fontSize="8"
              textAnchor={index === 0 ? 'start' : index === kmTicks.length - 1 ? 'end' : 'middle'}
            >
              {km}
              {index === kmTicks.length - 1 ? ' km' : ''}
            </text>
          </g>
        ))}

        {/* ravitos au contact exact de l'altitude + heure de passage de travers */}
        {ravitos.map((row) => {
          const px = xForKm(row.km);
          const py = yForAlt(altAt(row.km));
          return (
            <g key={`ravito-${row.name}-${row.km}`}>
              <line
                x1={px}
                x2={px}
                y1={py}
                y2={H - botAxis}
                stroke="var(--brand-sunset)"
                strokeWidth="1"
                strokeDasharray="2 2"
                opacity="0.45"
              />
              <circle cx={px} cy={py} r="3.2" fill="var(--brand-sunset)" stroke="var(--card)" strokeWidth="1.4" />
              <text
                x={px + 3}
                y={py - 6}
                fill="var(--brand-sunset)"
                fontSize="8"
                fontWeight="700"
                textAnchor="start"
                transform={`rotate(-45 ${px + 3} ${py - 6})`}
              >
                {row.predictedClock}
              </text>
            </g>
          );
        })}

        {/* altitudes min / max */}
        <text x="2" y={topPad - 4} fill="var(--muted-foreground)" fontSize="8">
          {Math.round(maxAlt)} m
        </text>
        <text x="2" y={H - botAxis - 3} fill="var(--muted-foreground)" fontSize="8">
          {Math.round(minAlt)} m
        </text>
      </svg>
    </div>
  );
}

function PacingCheckpointCards({
  rows,
  embedded = false,
}: {
  rows: CoursePacingRow[];
  embedded?: boolean;
}) {
  const timeline = (
    <div className="relative">
      {/* fil vertical de la timeline */}
      <div className="absolute bottom-3.5 left-[13px] top-3.5 z-0 w-0.5 bg-border-subtle" />
      <div className="relative z-10 flex flex-col gap-2">
        {rows.map((row) => (
          <PacingCheckpointCard key={`${row.name}-${row.km}`} row={row} />
        ))}
      </div>
    </div>
  );

  if (embedded) return timeline;

  return (
    <section className="rounded-md border border-border-subtle bg-card p-4">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="text-eyebrow">Temps de passage</p>
        <span className="text-[11px] text-muted-foreground">{rows.length} points</span>
      </div>
      {timeline}
    </section>
  );
}

function PacingCheckpointCard({ row }: { row: CoursePacingRow }) {
  const dot = pacingDotColor(row.service);
  const hasService = isOfficialAidPoint(row);
  const cells: Array<{ label: string; value: string; warn?: boolean }> = [
    { label: 'D+', value: `+${Math.round(row.elevationGainM)}m` },
    { label: 'Alt.', value: `${Math.round(row.altitudeM)}m` },
    { label: 'Chrono', value: formatPacingDuration(row.predictedElapsedMin) },
    { label: 'Barriere', value: row.lastTime || '—', warn: Boolean(row.lastTime) },
  ];

  return (
    <div className="flex items-start gap-3">
      <div className="flex w-7 shrink-0 justify-center pt-3.5">
        <span
          className="h-3.5 w-3.5 rounded-full"
          style={{
            background: dot,
            border: '3px solid var(--background)',
            boxShadow: `0 0 0 1px ${dot}`,
          }}
        />
      </div>
      <article className="min-w-0 flex-1 rounded-md border border-border-subtle bg-surface-2 p-3">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-foreground">{row.name}</p>
            <div className="mt-1 flex items-center gap-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground">
                km {formatKm(row.km)}
              </span>
              {hasService ? <ServiceBadge point={row} /> : null}
            </div>
          </div>
          <div className="shrink-0 text-right">
            <p
              className={`font-display text-xl font-bold leading-none ${
                row.isLate ? 'text-danger' : 'text-foreground'
              }`}
            >
              {row.predictedClock}
            </p>
            <p className="mt-1 text-[9px] uppercase tracking-[0.05em] text-muted-foreground">
              Passage
            </p>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-px overflow-hidden rounded bg-border-subtle">
          {cells.map((cell) => (
            <div key={cell.label} className="bg-card px-1 py-1.5 text-center">
              <p
                className={`text-xs font-bold leading-none ${
                  cell.warn ? 'text-warning-fg' : 'text-foreground'
                }`}
              >
                {cell.value}
              </p>
              <p className="mt-1 text-[8px] uppercase tracking-[0.04em] text-muted-foreground">
                {cell.label}
              </p>
            </div>
          ))}
        </div>

        {row.isLate ? (
          <div className="mt-2 flex items-center gap-1.5 rounded bg-danger-bg px-2 py-1.5">
            <AlertTriangle className="h-3 w-3 text-danger-fg" />
            <span className="text-[10px] font-semibold text-danger-fg">
              Risque hors delai sur barriere
            </span>
          </div>
        ) : null}
      </article>
    </div>
  );
}

function PacingCompleteTable({
  prediction,
  rows,
  totalTime,
  embedded = false,
}: {
  prediction: RacePredictionResult;
  rows: CoursePacingRow[];
  totalTime: number;
  embedded?: boolean;
}) {
  const table = (
    <div className={embedded ? '-mx-3 overflow-x-auto px-3' : '-mx-4 overflow-x-auto px-4'}>
      <table className="min-w-[900px] border-separate border-spacing-0 text-left text-[11px]">
        <thead>
          <tr className="text-muted-foreground">
            <th className="sticky left-0 z-10 border-b border-border-subtle bg-card py-2 pr-3 font-semibold">
              Point
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              Km
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              Prévu
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              H. de pass.
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              Barrière
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              Météo
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              Type
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              Pause
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              D+
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              D-
            </th>
            <th className="border-b border-border-subtle px-2 py-2 font-semibold">
              Alt.
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.name}-${row.km}`} className="border-b border-border-subtle">
              <td className="sticky left-0 z-10 border-b border-border-subtle bg-card py-2 pr-3">
                <p className="max-w-[150px] truncate font-semibold text-foreground">
                  {row.name}
                </p>
              </td>
              <td className="border-b border-border-subtle px-2 py-2 text-foreground">
                {formatKm(row.km)}
              </td>
              <td className="border-b border-border-subtle px-2 py-2">
                <span
                  className={`block font-semibold ${row.isLate ? 'text-danger' : 'text-foreground'}`}
                >
                  {formatPacingDuration(row.predictedElapsedMin)}
                </span>
                {row.cutoffDeltaMin != null ? (
                  <span
                    className={`block text-[10px] ${row.isLate ? 'text-danger' : 'text-muted-foreground'}`}
                  >
                    {signedMinutes(row.cutoffDeltaMin)}
                  </span>
                ) : null}
              </td>
              <td className="border-b border-border-subtle px-2 py-2">
                <span
                  className={`font-semibold ${row.isLate ? 'text-danger' : 'text-brand-cyan'}`}
                >
                  {row.predictedClock}
                </span>
              </td>
              <td className="border-b border-border-subtle px-2 py-2">
                <span
                  className={
                    row.cutoffLabel
                      ? 'font-semibold text-warning-fg'
                      : 'text-muted-foreground'
                  }
                >
                  {row.cutoffLabel ?? row.lastTime ?? '--'}
                </span>
              </td>
              <td className="border-b border-border-subtle px-2 py-2">
                <WeatherTag prediction={prediction} elapsedMin={row.predictedElapsedMin} />
              </td>
              <td className="border-b border-border-subtle px-2 py-2">
                <ServiceBadge point={row} />
              </td>
              <td className="border-b border-border-subtle px-2 py-2 text-muted-foreground">
                {row.pauseMin && row.pauseMin > 0 ? formatMinutes(row.pauseMin) : '--'}
              </td>
              <td className="border-b border-border-subtle px-2 py-2 text-muted-foreground">
                +{row.elevationGainM}
              </td>
              <td className="border-b border-border-subtle px-2 py-2 text-muted-foreground">
                -{row.elevationLossM}
              </td>
              <td className="border-b border-border-subtle px-2 py-2 text-muted-foreground">
                {row.altitudeM}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  if (embedded) return table;

  return (
    <section className="rounded-md border border-border-subtle bg-card p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-foreground">Table complete</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Vue detaillee des barrieres, services, pauses, D+ cumule et meteo.
          </p>
        </div>
        <span className="bg-brand-primary/10 rounded-full px-2 py-1 text-[11px] font-semibold text-brand-cyan">
          {formatPacingDuration(totalTime)}
        </span>
      </div>
      {table}
    </section>
  );
}

function ServiceBadge({ point }: { point: CoursePacingPoint }) {
  const label = isFoodRavito(point)
    ? point.service === 'hot_food'
      ? 'Ravito chaud'
      : 'Ravito'
    : point.service === 'drink'
      ? 'Boisson'
      : point.service === 'finish'
        ? 'Arrivee'
        : point.service === 'start'
          ? 'Depart'
          : 'Passage';
  const tone = isFoodRavito(point)
    ? 'border-brand-primary/30 bg-brand-primary/10 text-brand-cyan'
    : point.service === 'drink'
      ? 'border-brand-cyan/30 bg-brand-cyan/10 text-brand-cyan'
      : 'border-border-subtle bg-surface-2 text-muted-foreground';

  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full border px-2 py-1 text-[10px] font-semibold ${tone}`}
    >
      {label}
    </span>
  );
}

function PredictionAnalyticsMobile() {
  const queryClient = useQueryClient();
  const [predictionId, setPredictionId] = useState('');
  const [activityId, setActivityId] = useState('');
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
  const predictionsQuery = useQuery({
    queryKey: ['agon', 'race-predictions'],
    queryFn: () => agonApi.getSavedRacePredictions(),
  });
  const activitiesQuery = useQuery({
    queryKey: ['agon', 'activities', 'analytics', oneYearAgoIsoDate()],
    queryFn: () =>
      agonApi.getEnrichedActivities({
        page: 1,
        per_page: 100,
        date_from: oneYearAgoIsoDate(),
      }),
  });
  const candidatesQuery = useQuery({
    queryKey: ['agon', 'race-reference-candidates', 'pending'],
    queryFn: () => agonApi.getRaceReferenceCandidates('pending'),
  });
  const detectCandidatesMutation = useMutation({
    mutationFn: () =>
      agonApi.detectRaceReferenceCandidates({
        history_start_date: oneYearAgoIsoDate(),
        limit: 250,
      }),
    onSuccess: (data) => {
      toast.success(`${data.detected_count} reference(s) candidate(s) detectee(s)`);
      queryClient.invalidateQueries({ queryKey: ['agon', 'race-reference-candidates'] });
      queryClient.invalidateQueries({ queryKey: ['agon', 'race-validation-references'] });
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Detection impossible'),
  });
  const resolveCandidateMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'accept' | 'reject' }) =>
      agonApi.resolveRaceReferenceCandidate(id, { action }),
    onSuccess: (_, variables) => {
      toast.success(
        variables.action === 'accept' ? 'Reference ajoutee' : 'Candidate rejetee',
      );
      queryClient.invalidateQueries({ queryKey: ['agon', 'race-reference-candidates'] });
      queryClient.invalidateQueries({ queryKey: ['agon', 'race-validation-references'] });
    },
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Action impossible'),
  });
  const compareMutation = useMutation({
    mutationFn: () => agonApi.compareRacePrediction(predictionId, activityId),
    onSuccess: setComparison,
    onError: (error) =>
      toast.error(error instanceof Error ? error.message : 'Comparaison impossible'),
  });

  const predictions = useMemo(
    () =>
      (predictionsQuery.data?.items ?? []).filter((item) =>
        ['v1_random_forest', 'v2_physics', 'v3_hybrid', 'v2_3_1_bayesian'].includes(
          item.engine_version ?? '',
        ),
      ),
    [predictionsQuery.data?.items],
  );
  const activities = activitiesQuery.data?.items ?? [];
  const candidates = candidatesQuery.data?.items ?? [];

  return (
    <section className="space-y-4">
      <div className="rounded-md border border-border-subtle bg-card p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <Activity className="h-5 w-5 shrink-0 text-brand-cyan" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">
                References detectees
              </p>
              <p className="text-xs text-muted-foreground">
                Activites utiles pour apprendre ton profil sans tag manuel lourd.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => detectCandidatesMutation.mutate()}
            disabled={detectCandidatesMutation.isPending}
            className="bg-surface-2 rounded-md border border-border-subtle px-3 py-2 text-xs font-semibold text-foreground"
          >
            {detectCandidatesMutation.isPending ? 'Scan...' : 'Scanner'}
          </button>
        </div>
        {candidatesQuery.isLoading ? (
          <p className="bg-surface-2 rounded-md p-3 text-xs text-muted-foreground">
            Analyse des activites...
          </p>
        ) : candidates.length ? (
          <div className="space-y-2">
            {candidates.slice(0, 5).map((candidate) => (
              <ReferenceCandidateCard
                key={candidate.id}
                candidate={candidate}
                isBusy={resolveCandidateMutation.isPending}
                onAccept={() =>
                  resolveCandidateMutation.mutate({ id: candidate.id, action: 'accept' })
                }
                onReject={() =>
                  resolveCandidateMutation.mutate({ id: candidate.id, action: 'reject' })
                }
              />
            ))}
            {candidates.length > 5 ? (
              <p className="text-xs text-muted-foreground">
                +{candidates.length - 5} autre(s) candidat(s) en attente.
              </p>
            ) : null}
          </div>
        ) : (
          <p className="bg-surface-2 rounded-md p-3 text-xs text-muted-foreground">
            Aucune candidate en attente. Le scan se relance aussi apres
            sync/enrichissement Garmin.
          </p>
        )}
      </div>

      <div className="rounded-md border border-border-subtle bg-card p-4">
        <div className="mb-3 flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-brand-cyan" />
          <div>
            <p className="text-sm font-semibold text-foreground">Analytics</p>
            <p className="text-xs text-muted-foreground">
              Prediction sauvegardee vs activite reelle.
            </p>
          </div>
        </div>
        <div className="space-y-3">
          <MobileSelect
            label="Prediction"
            value={predictionId}
            onChange={setPredictionId}
            options={[
              ['', 'Choisir'],
              ...predictions.map(
                (prediction) =>
                  [prediction.id, predictionLabel(prediction)] as [string, string],
              ),
            ]}
          />
          <MobileSelect
            label="Activite"
            value={activityId}
            onChange={setActivityId}
            options={[
              ['', 'Choisir'],
              ...activities.map(
                (activity) =>
                  [activityDisplayId(activity), activity.name] as [string, string],
              ),
            ]}
          />
          <button
            type="button"
            onClick={() => compareMutation.mutate()}
            disabled={!predictionId || !activityId || compareMutation.isPending}
            className="btn-glass-primary w-full"
          >
            {compareMutation.isPending ? 'Analyse...' : 'Comparer'}
          </button>
        </div>
        {comparison ? <ComparisonSummary comparison={comparison} /> : null}
      </div>
    </section>
  );
}

function ReferenceCandidateCard({
  candidate,
  isBusy,
  onAccept,
  onReject,
}: {
  candidate: RaceReferenceCandidate;
  isBusy: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  const featureDistance = Number(
    candidate.features?.distance_km ?? candidate.activity?.distance_km ?? 0,
  );
  const featureDuration = Number(
    candidate.features?.duration_min ?? candidate.activity?.moving_time_min ?? 0,
  );
  const featureElevation = Number(
    candidate.features?.elevation_gain_m ?? candidate.activity?.elevation_gain_m ?? 0,
  );
  const reasonSummary = [
    ...(candidate.reasons?.positive ?? []),
    ...(candidate.reasons?.anomalies ?? []),
    ...(candidate.reasons?.negative ?? []),
  ].slice(0, 3);

  return (
    <div className="bg-surface-2 rounded-md border border-border-subtle p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">
            {candidate.activity?.name ?? String(candidate.features?.name ?? 'Activite')}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {referenceCategoryLabel(candidate.suggested_category)} · score{' '}
            {Math.round(candidate.score)} · {candidate.confidence}
          </p>
        </div>
        <span className="rounded bg-[var(--chip-bg)] px-2 py-1 text-[11px] font-semibold text-brand-cyan">
          {candidate.status}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-muted-foreground">
        <span>{featureDistance > 0 ? `${featureDistance.toFixed(1)} km` : '--'}</span>
        <span>{featureDuration > 0 ? formatMinutes(featureDuration) : '--'}</span>
        <span>
          {featureElevation > 0 ? `+${Math.round(featureElevation)} m` : '+0 m'}
        </span>
      </div>
      {reasonSummary.length ? (
        <div className="mt-3 flex flex-wrap gap-1">
          {reasonSummary.map((reason) => (
            <span
              key={reason}
              className="rounded bg-[var(--chip-bg)] px-2 py-1 text-[10px] text-muted-foreground"
            >
              {referenceReasonLabel(reason)}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          disabled={isBusy}
          onClick={onReject}
          className="rounded-md border border-border-subtle px-3 py-2 text-xs font-semibold text-muted-foreground"
        >
          Rejeter
        </button>
        <button
          type="button"
          disabled={isBusy}
          onClick={onAccept}
          className="rounded-md bg-brand-primary px-3 py-2 text-xs font-semibold text-white"
        >
          Accepter
        </button>
      </div>
    </div>
  );
}

function ComparisonSummary({ comparison }: { comparison: Record<string, unknown> }) {
  const summary = comparison.summary as Record<string, unknown> | undefined;
  const totalDelta = Number(summary?.total_delta_min ?? 0);
  const movingDelta = Number(summary?.moving_delta_min ?? 0);
  const avgSegment = Number(summary?.avg_abs_segment_delta_min ?? 0);
  return (
    <div className="bg-surface-2 mt-4 rounded-md border border-border-subtle p-3">
      <p className="mb-3 text-sm font-semibold text-foreground">Ecarts</p>
      <div className="grid grid-cols-3 gap-2">
        <ResultCard label="Total" value={signedMinutes(totalDelta)} />
        <ResultCard label="Moving" value={signedMinutes(movingDelta)} />
        <ResultCard label="Segment" value={`${avgSegment.toFixed(1)}m`} />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">
        Negatif : prediction trop rapide. Positif : prediction trop prudente.
      </p>
    </div>
  );
}

function AttachmentsModal({
  route,
  onClose,
  onOpen,
}: {
  route: GpxRouteDetail;
  onClose: () => void;
  onOpen: (attachment: GpxAttachmentRead) => void;
}) {
  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 backdrop-blur-sm md:items-center"
      onClick={onClose}
    >
      <div
        className="mx-4 mb-4 w-full max-w-md rounded-md border border-border-subtle bg-card p-4 shadow-xl md:mb-0"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-eyebrow">Infos complementaires</p>
            <p className="mt-0.5 text-sm font-semibold text-foreground">{route.name}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Fermer
          </button>
        </div>
        <ul className="space-y-2">
          {route.attachments.map((attachment) => (
            <li key={attachment.id}>
              <button
                type="button"
                onClick={() => onOpen(attachment)}
                className="bg-surface-2 flex w-full items-center gap-3 rounded-md border border-border-subtle p-3 text-left transition hover:bg-[var(--hover-overlay)]"
              >
                <FileText className="h-5 w-5 shrink-0 text-brand-cyan" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-foreground">
                    {attachment.name}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {attachment.filename}
                  </p>
                </div>
                <span className="text-[11px] uppercase text-muted-foreground">
                  {attachment.kind}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function MobileSelect({
  label,
  value,
  onChange,
  options,
  compact = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<[string, string]>;
  compact?: boolean;
}) {
  return (
    <label className={compact ? 'block w-28' : 'block'}>
      {label ? (
        <span className="mb-1 block text-xs text-muted-foreground">{label}</span>
      ) : null}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="bg-surface-2 w-full rounded-md border border-border-subtle px-3 py-2 text-sm"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function DetailDisclosure({
  title,
  icon,
  children,
  defaultOpen = false,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  return (
    <details
      open={defaultOpen}
      className="rounded-md border border-border-subtle bg-card"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-3 text-sm font-semibold text-foreground">
        <span className="flex items-center gap-2">
          {icon}
          {title}
        </span>
        <ChevronDown className="h-4 w-4 text-muted-foreground" />
      </summary>
      <div className="border-t border-border-subtle p-3">{children}</div>
    </details>
  );
}

function TechnicalSubsection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </p>
      {children}
    </div>
  );
}

function KeyValueGrid({ data, keys }: { data: unknown; keys: Array<[string, string]> }) {
  const record = asRecord(data);
  const rows = keys
    .map(([key, label]) => [label, nested(record, key)] as [string, unknown])
    .filter(([, value]) => value !== undefined && value !== null && value !== '');

  if (!rows.length) {
    return (
      <p className="text-xs text-muted-foreground">
        Donnee non disponible pour ce moteur.
      </p>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-2">
      {rows.map(([label, value]) => (
        <div key={label} className="bg-surface-2 rounded-md p-3">
          <p className="text-[11px] text-muted-foreground">{label}</p>
          <p className="mt-1 truncate text-sm font-semibold text-foreground">
            {formatValue(value)}
          </p>
        </div>
      ))}
    </div>
  );
}

function ResultCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-surface-2 rounded-md p-3">
      <p className="text-base font-bold leading-none text-foreground">{value}</p>
      <p className="mt-1 text-[11px] text-muted-foreground">{label}</p>
    </div>
  );
}

function routeOptionLabel(route: GpxRouteSummary): string {
  const dist = route.distance_km != null ? ` · ${route.distance_km.toFixed(0)} km` : '';
  const tag = route.is_public ? '' : ' (perso)';
  const docs = route.attachment_count > 0 ? ` · ${route.attachment_count} info` : '';
  return `${route.name}${dist}${docs}${tag}`;
}

function coursePlanForRoute(route: GpxRouteDetail | null): CoursePacingPoint[] | null {
  if (!route) return null;
  return coursePlanFromText(route.name, route.filename);
}

function coursePlanForPrediction(
  prediction: SavedRacePrediction,
): CoursePacingPoint[] | null {
  return coursePlanFromText(
    prediction.name,
    prediction.filename,
    prediction.prediction_data?.filename,
  );
}

function coursePlanForPredictionResult(
  prediction: RacePredictionResult,
  name: string,
): CoursePacingPoint[] | null {
  return (
    coursePlanFromText(name, prediction.filename) ??
    coursePlanFromPredictionData(prediction)
  );
}

function coursePlanFromPredictionData(
  prediction: RacePredictionResult,
): CoursePacingPoint[] | null {
  const totalDistance = metric(
    prediction,
    'total_distance_km',
    'summary.total_distance_km',
  );
  const segments = extractSegments(prediction);
  const ravitos = extractRavitoPoints(prediction);

  if (totalDistance <= 0 && !segments.length && !ravitos.length) return null;

  const finishKm =
    totalDistance > 0
      ? totalDistance
      : Math.max(
          ...segments.map((segment) =>
            Number(segment.to_km ?? segment.end_km ?? segment.distance_km ?? 0),
          ),
          0,
        );
  if (finishKm <= 0) return null;

  const startProfile = courseProfileAtKm(prediction, 0);
  const finishProfile = courseProfileAtKm(prediction, finishKm);
  const points: CoursePacingPoint[] = [
    {
      name: 'START',
      km: 0,
      elevationGainM: 0,
      elevationLossM: 0,
      altitudeM: startProfile.altitudeM,
      bestTime: '',
      lastTime: '',
      service: 'start',
    },
    ...ravitos
      .map((ravito, index): CoursePacingPoint | null => {
        const km = Number(ravito.distance_km ?? ravito.km ?? 0);
        if (!Number.isFinite(km) || km <= 0 || km >= finishKm) return null;
        const profile = courseProfileAtKm(prediction, km);
        return {
          name: String(ravito.name || `Ravito ${index + 1}`),
          km: roundOne(km),
          elevationGainM: profile.elevationGainM,
          elevationLossM: profile.elevationLossM,
          altitudeM: profile.altitudeM,
          bestTime: '',
          lastTime: '',
          pauseMin: Number(ravito.pause_min ?? 0),
          service: 'food',
        };
      })
      .filter((point): point is CoursePacingPoint => point != null),
    {
      name: 'FINISH',
      km: roundOne(finishKm),
      elevationGainM: finishProfile.elevationGainM,
      elevationLossM: finishProfile.elevationLossM,
      altitudeM: finishProfile.altitudeM,
      bestTime: '',
      lastTime: '',
      service: 'finish',
    },
  ];

  return points.sort((a, b) => a.km - b.km);
}

function courseProfileAtKm(
  prediction: RacePredictionResult,
  targetKm: number,
): Pick<CoursePacingPoint, 'elevationGainM' | 'elevationLossM' | 'altitudeM'> {
  const segments = extractSegments(prediction);
  if (!segments.length) {
    return { elevationGainM: 0, elevationLossM: 0, altitudeM: 0 };
  }

  let previousToKm = 0;
  let cumulativeGain = 0;
  let cumulativeLoss = 0;
  let altitude = Number(segments[0]?.altitude_m ?? 0);

  for (const segment of segments) {
    const explicitFrom = Number(segment.from_km);
    const distanceKm = Number(segment.distance_km ?? 0);
    const fromKm = Number.isFinite(explicitFrom) ? explicitFrom : previousToKm;
    const explicitTo = Number(segment.to_km ?? segment.end_km);
    const toKm = Number.isFinite(explicitTo) ? explicitTo : fromKm + distanceKm;
    const segmentGain = Number(segment.elevation_gain_m ?? segment.elevation_gain ?? 0);
    const segmentLoss = Number(segment.elevation_loss_m ?? segment.elevation_loss ?? 0);
    const segmentAltitude = Number(segment.altitude_m ?? altitude);

    if (targetKm >= toKm) {
      cumulativeGain += Number.isFinite(segmentGain) ? segmentGain : 0;
      cumulativeLoss += Number.isFinite(segmentLoss) ? segmentLoss : 0;
      if (Number.isFinite(segmentAltitude)) altitude = segmentAltitude;
      previousToKm = toKm;
      continue;
    }

    if (targetKm >= fromKm) {
      const ratio =
        toKm > fromKm
          ? Math.max(0, Math.min(1, (targetKm - fromKm) / (toKm - fromKm)))
          : 0;
      cumulativeGain += (Number.isFinite(segmentGain) ? segmentGain : 0) * ratio;
      cumulativeLoss += (Number.isFinite(segmentLoss) ? segmentLoss : 0) * ratio;
      if (Number.isFinite(segmentAltitude)) altitude = segmentAltitude;
    }
    break;
  }

  return {
    elevationGainM: Math.round(cumulativeGain),
    elevationLossM: Math.round(cumulativeLoss),
    altitudeM: Math.round(Number.isFinite(altitude) ? altitude : 0),
  };
}

function coursePlanFromText(
  ...values: Array<string | null | undefined>
): CoursePacingPoint[] | null {
  const text = values.filter(Boolean).join(' ').toLowerCase();
  if (text.includes('swiss canyon') || text.includes('111k'))
    return SWISS_CANYON_111K_POINTS;
  return null;
}

function isFoodRavito(point: CoursePacingPoint): boolean {
  return point.service === 'food' || point.service === 'hot_food';
}

function isOfficialAidPoint(point: CoursePacingPoint): boolean {
  return isFoodRavito(point) || point.service === 'drink';
}

function officialPauseMin(point: CoursePacingPoint): number {
  if (point.service === 'drink') return 1.5;
  if (point.service === 'hot_food' || point.baseLife || point.personalBag) return 5;
  return 3;
}

function officialRavitosFromCoursePlan(
  points: CoursePacingPoint[] | null,
): RouteRavitoPoint[] {
  if (!points) return [];
  return points
    .filter((point) => point.km > 0 && isOfficialAidPoint(point))
    .map((point) => ({
      km: roundOne(point.km),
      name: point.name,
      pause_min: officialPauseMin(point),
    }));
}

function buildCoursePacingRows(
  prediction: RacePredictionResult,
  points: CoursePacingPoint[],
  startClock: PacingStartClock | null,
): CoursePacingRow[] {
  const total = metric(prediction, 'total_time_min', 'summary.total_time_min');
  let previousGain = 0;
  let previousLoss = 0;

  return points.map((point) => {
    const predictedElapsedMin =
      point.service === 'finish' ? total : predictedElapsedAtKm(prediction, point.km);
    const weather = weatherAtElapsed(prediction, predictedElapsedMin);
    const cutoffDeltaMin =
      point.cutoffElapsedMin != null
        ? predictedElapsedMin - point.cutoffElapsedMin
        : null;
    const row: CoursePacingRow = {
      ...point,
      predictedElapsedMin,
      predictedClock: formatPredictedClock(startClock, predictedElapsedMin),
      isLate: cutoffDeltaMin != null && cutoffDeltaMin > 0,
      cutoffDeltaMin,
      segmentGainM: Math.max(0, point.elevationGainM - previousGain),
      segmentLossM: Math.max(0, point.elevationLossM - previousLoss),
      pauseMin: point.pauseMin ?? (isOfficialAidPoint(point) ? officialPauseMin(point) : 0),
      temperatureC: weather?.tempC ?? null,
      heatPenaltyPct: weather?.heatPenaltyPct ?? 0,
    };
    previousGain = point.elevationGainM;
    previousLoss = point.elevationLossM;
    return row;
  });
}

function formatKm(km: number): string {
  if (!Number.isFinite(km)) return '--';
  return km % 1 === 0 ? km.toFixed(0) : km.toFixed(1);
}

function formatPacingDuration(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes < 0) return '--';
  if (minutes === 0) return '0 min';
  const rounded = Math.round(minutes);
  const h = Math.floor(rounded / 60);
  const m = rounded % 60;
  if (h <= 0) return `${m} min`;
  return `${h}h${String(m).padStart(2, '0')}`;
}

function formatCutoffStatus(deltaMin: number): string {
  if (!Number.isFinite(deltaMin)) return '--';
  if (deltaMin > 0) return `+${formatPacingDuration(deltaMin)}`;
  if (deltaMin < 0) return `-${formatPacingDuration(Math.abs(deltaMin))}`;
  return 'pile';
}

function mergeOfficialRavitos(
  officialRavitos: RouteRavitoPoint[],
  currentRavitos: RouteRavitoPoint[],
): RouteRavitoPoint[] {
  if (!officialRavitos.length) return normalizeRavitos(currentRavitos);
  const current = normalizeRavitos(currentRavitos);
  return officialRavitos.map((official) => {
    const match = current.find(
      (candidate) =>
        Math.abs(Number(candidate.km) - Number(official.km)) < 0.05 ||
        normalizeRavitoName(candidate.name) === normalizeRavitoName(official.name),
    );
    return {
      ...official,
      pause_min: roundOne(Number(match?.pause_min ?? official.pause_min)),
    };
  });
}

function normalizeRavitoName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function pacingStartClock(
  prediction: RacePredictionResult,
  points: CoursePacingPoint[],
): PacingStartClock | null {
  const startTime = points.find((point) => point.service === 'start')?.bestTime;
  const officialStartClock = parseStartClock(startTime);
  const localRaceDatetime = nested(prediction, 'race_datetime_local');
  if (typeof localRaceDatetime === 'string' && localRaceDatetime) {
    return parseRaceClock(localRaceDatetime);
  }

  const raceDatetime = nested(prediction, 'race_datetime');
  if (typeof raceDatetime === 'string' && raceDatetime) {
    const hasTimezone = /(?:z|[+-]\d{2}:\d{2})$/i.test(raceDatetime);
    if (!hasTimezone && officialStartClock) return officialStartClock;
    return parseRaceClock(raceDatetime);
  }
  return officialStartClock;
}

function parseRaceClock(value: string): PacingStartClock | null {
  const wallClock = parseDatetimeLocalParts(value);
  if (wallClock) {
    return {
      date: new Date(
        wallClock.year,
        wallClock.month - 1,
        wallClock.day,
        wallClock.hours,
        wallClock.minutes,
      ),
      minutesOfDay: wallClock.hours * 60 + wallClock.minutes,
    };
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return {
    date,
    minutesOfDay: date.getHours() * 60 + date.getMinutes(),
  };
}

function parseDatetimeLocalParts(value: string): {
  year: number;
  month: number;
  day: number;
  hours: number;
  minutes: number;
} | null {
  const match = value.match(
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?$/,
  );
  if (!match) return null;
  const year = Number(match[1] ?? Number.NaN);
  const month = Number(match[2] ?? Number.NaN);
  const day = Number(match[3] ?? Number.NaN);
  const hours = Number(match[4] ?? Number.NaN);
  const minutes = Number(match[5] ?? Number.NaN);
  if (
    !Number.isFinite(year) ||
    !Number.isFinite(month) ||
    !Number.isFinite(day) ||
    !Number.isFinite(hours) ||
    !Number.isFinite(minutes) ||
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > 31 ||
    hours > 23 ||
    minutes > 59
  ) {
    return null;
  }
  return { year, month, day, hours, minutes };
}

function parseStartClock(value: string | undefined): PacingStartClock | null {
  const match = value?.match(/^(\d{1,2}):(\d{2})/);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || hours > 23 || minutes > 59)
    return null;
  return { date: null, minutesOfDay: hours * 60 + minutes };
}

function formatPredictedClock(
  startClock: PacingStartClock | null,
  elapsedMin: number,
): string {
  if (!startClock || !Number.isFinite(elapsedMin)) return '--';
  const elapsedRounded = Math.round(elapsedMin);
  if (startClock.date) {
    const target = new Date(startClock.date.getTime() + elapsedRounded * 60_000);
    const startDay = new Date(
      startClock.date.getFullYear(),
      startClock.date.getMonth(),
      startClock.date.getDate(),
    ).getTime();
    const targetDay = new Date(
      target.getFullYear(),
      target.getMonth(),
      target.getDate(),
    ).getTime();
    const dayOffset = Math.max(0, Math.round((targetDay - startDay) / 86_400_000));
    return formatClockParts(target.getHours(), target.getMinutes(), dayOffset);
  }

  const totalMinutes = startClock.minutesOfDay + elapsedRounded;
  const dayOffset = Math.floor(totalMinutes / 1440);
  const minutesOfDay = ((totalMinutes % 1440) + 1440) % 1440;
  return formatClockParts(Math.floor(minutesOfDay / 60), minutesOfDay % 60, dayOffset);
}

function formatClockParts(hours: number, minutes: number, dayOffset: number): string {
  const clock = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
  return dayOffset > 0 ? `${clock} +J${dayOffset}` : clock;
}

function predictedElapsedAtKm(
  prediction: RacePredictionResult,
  targetKm: number,
): number {
  if (!Number.isFinite(targetKm) || targetKm <= 0) return 0;
  const segments = extractSegments(prediction);
  if (!segments.length) return 0;

  let previousToKm = 0;
  let previousMovingMin = 0;
  for (const segment of segments) {
    const explicitFrom = Number(segment.from_km);
    const distanceKm = Number(segment.distance_km ?? 0);
    const fromKm = Number.isFinite(explicitFrom) ? explicitFrom : previousToKm;
    const explicitTo = Number(segment.to_km);
    const toKm = Number.isFinite(explicitTo) ? explicitTo : fromKm + distanceKm;
    const segmentMovingTime = Number(
      segment.predicted_time_min ?? segment.segment_time_min ?? 0,
    );
    const explicitEndMoving = Number(segment.cumulative_moving_time_min);
    const endMovingMin =
      Number.isFinite(explicitEndMoving) && explicitEndMoving > 0
        ? explicitEndMoving
        : previousMovingMin + segmentMovingTime;
    const startMovingMin = Math.max(0, endMovingMin - segmentMovingTime);

    if (targetKm <= toKm || segment === segments[segments.length - 1]) {
      const ratio =
        toKm > fromKm
          ? Math.max(0, Math.min(1, (targetKm - fromKm) / (toKm - fromKm)))
          : 0;
      const movingAtPoint = startMovingMin + (endMovingMin - startMovingMin) * ratio;
      return movingAtPoint + pauseBeforeKm(prediction, targetKm);
    }

    previousToKm = toKm;
    previousMovingMin = endMovingMin;
  }

  return metric(prediction, 'total_time_min', 'summary.total_time_min');
}

function pauseBeforeKm(prediction: RacePredictionResult, targetKm: number): number {
  return extractRavitoPoints(prediction).reduce((total, ravito) => {
    const distanceKm = Number(ravito.distance_km ?? ravito.km ?? 0);
    if (distanceKm > 0 && distanceKm < targetKm - 0.01) {
      return total + Number(ravito.pause_min ?? 0);
    }
    return total;
  }, 0);
}

function predictionLabel(prediction: SavedRacePrediction): string {
  const engine =
    prediction.engine_version === 'v3_hybrid' ||
    prediction.engine_version === 'v2_3_1_bayesian'
      ? 'V3'
      : prediction.engine_version === 'v2_physics'
        ? 'V2'
        : 'V1';
  const total = prediction.total_time_min
    ? ` · ${formatMinutes(prediction.total_time_min)}`
    : '';
  return `${engine} · ${prediction.name}${total}`;
}

function referenceCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    official_clean: 'Course propre',
    official_normalized: 'Course a normaliser',
    training_control: 'Seance repere',
    incident_non_scoring: 'Incident non scorant',
  };
  return labels[category] ?? category;
}

function referenceReasonLabel(reason: string): string {
  const labels: Record<string, string> = {
    event_like_name: 'nom de course',
    typical_race_distance: 'distance typique',
    trail_profile: 'profil trail',
    complete_garmin_streams: 'streams complets',
    high_hr_intensity: 'FC elevee',
    moderate_hr_intensity: 'FC soutenue',
    meaningful_duration: 'duree utile',
    fast_for_user_history: 'rapide pour toi',
    long_pause_detected: 'pause longue',
    severe_late_fade: 'grosse derive finale',
    incident_keyword: 'incident detecte',
    low_hr_intensity: 'intensite basse',
    training_or_recovery_name: 'nom entrainement',
  };
  return labels[reason] ?? reason.replaceAll('_', ' ');
}

function metric(prediction: RacePredictionResult, ...paths: string[]): number {
  for (const path of paths) {
    const value = nested(prediction, path);
    const numberValue = Number(value);
    if (Number.isFinite(numberValue)) return numberValue;
  }
  return 0;
}

function nested(source: unknown, path: string): unknown {
  const chunks = path.split('.');
  let cursor: unknown = source;
  for (const chunk of chunks) {
    if (!cursor || typeof cursor !== 'object') return undefined;
    cursor = (cursor as Record<string, unknown>)[chunk];
  }
  return cursor;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function extractRavitoPoints(
  prediction: RacePredictionResult,
): Array<Record<string, unknown>> {
  const ravitos = prediction.ravitos as
    | { points?: Array<Record<string, unknown>> }
    | undefined;
  if (Array.isArray(ravitos?.points)) return ravitos.points;
  if (Array.isArray(prediction.ravito_points))
    return prediction.ravito_points as Array<Record<string, unknown>>;
  return [];
}

function extractSegments(
  prediction: RacePredictionResult,
): Array<Record<string, unknown>> {
  return Array.isArray(prediction.segments) ? prediction.segments : [];
}

function normalizeRavitos(input: unknown): RouteRavitoPoint[] {
  if (!Array.isArray(input)) return [];
  return input
    .map((item, index) => {
      const record = asRecord(item);
      return {
        km: roundOne(Number(record.km ?? record.distance_km ?? 0)),
        name: String(record.name ?? `Ravito ${index + 1}`),
        pause_min: roundOne(Number(record.pause_min ?? 0)),
      };
    })
    .filter((item) => item.km > 0);
}

// Température (et pénalité chaleur) au temps écoulé donné, lue dans la timeline
// météo de la prédiction (environment.exposure_timeline, indexée en minutes
// moving — cohérent avec predictedElapsedAtKm).
function weatherAtElapsed(
  prediction: RacePredictionResult,
  elapsedMin: number,
): { tempC: number; heatPenaltyPct: number } | null {
  const env = prediction.environment as Record<string, unknown> | undefined;
  const timeline = (env?.exposure_timeline ?? env?.weather_timeline) as
    | Array<Record<string, number>>
    | undefined;
  if (!Array.isArray(timeline) || timeline.length === 0) return null;
  let best = timeline[0];
  if (!best) return null;
  for (const entry of timeline) {
    if (
      Math.abs(Number(entry.elapsed_min) - elapsedMin) <
      Math.abs(Number(best.elapsed_min) - elapsedMin)
    ) {
      best = entry;
    }
  }
  const tempC = Number(best.temperature_c);
  if (!Number.isFinite(tempC)) return null;
  return { tempC, heatPenaltyPct: Number(best.heat_penalty_percent ?? 0) };
}

// Petit badge météo (température à l'heure de passage). Vire à l'orange si la
// pénalité chaleur est notable.
function WeatherTag({
  prediction,
  elapsedMin,
}: {
  prediction: RacePredictionResult;
  elapsedMin: number;
}) {
  const weather = weatherAtElapsed(prediction, elapsedMin);
  if (!weather) return null;
  const hot = weather.heatPenaltyPct >= 5;
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap text-[11px] ${hot ? 'text-warning-fg' : 'text-muted-foreground'}`}
      title={`Pénalité chaleur +${Math.round(weather.heatPenaltyPct)}%`}
    >
      {Math.round(weather.tempC)}°C
      {weather.heatPenaltyPct >= 1 ? ` · +${Math.round(weather.heatPenaltyPct)}%` : ''}
    </span>
  );
}

function formatMinutes(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return '--';
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h <= 0) return `${m} min`;
  return `${h}h${String(m).padStart(2, '0')}`;
}

function signedMinutes(minutes: number): string {
  if (!Number.isFinite(minutes)) return '--';
  const sign = minutes > 0 ? '+' : minutes < 0 ? '-' : '';
  return `${sign}${Math.abs(minutes).toFixed(1)}m`;
}

function formatValue(value: unknown): string {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return '--';
    return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(2);
  }
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'oui' : 'non';
  return JSON.stringify(value);
}

function roundOne(value: number): number {
  return Number.isFinite(value) ? Math.round(value * 10) / 10 : 0;
}

function toEngine(value: string | null | undefined): Engine {
  return value === 'v1' || value === 'v2' || value === 'v3' ? value : 'v3';
}

function toAnalysisMode(value: string | null | undefined): AnalysisMode {
  return value === 'route' || value === 'trail' || value === 'auto' ? value : 'auto';
}

function toEffortMode(value: string | null | undefined): EffortMode {
  return value === 'endurance' || value === 'aggressive' || value === 'steady'
    ? value
    : 'steady';
}

function toRavitoMode(value: string | null | undefined): RavitoMode {
  return value === 'manual' ? 'manual' : 'auto';
}

function toWeatherMode(value: string | null | undefined): WeatherMode {
  return value === 'manual' ? 'manual' : 'auto';
}

function serializeDatetimeLocal(value: string): string | null {
  return value ? value.slice(0, 16) : null;
}

function toDatetimeLocal(value: string | null | undefined): string {
  if (!value) return '';
  if (parseDatetimeLocalParts(value)) return value.slice(0, 16);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
