import { useSyncExternalStore } from 'react';
import {
  agonApi,
  type GarminImportPreview,
  type GarminImportStatus,
} from '@/lib/api/agon';

export const IMPORT_PERIOD_OPTIONS = [
  { value: 7, label: '7 derniers jours' },
  { value: 14, label: '14 derniers jours' },
  { value: 30, label: '30 derniers jours' },
  { value: 60, label: '2 derniers mois' },
  { value: 90, label: '3 derniers mois' },
  { value: 180, label: '6 derniers mois' },
  { value: 365, label: '1 an' },
  { value: 730, label: '2 ans' },
] as const;

export const DEFAULT_IMPORT_DAYS_BACK = 30;

const FIT_BATCH_SIZE = 1;
const MAX_IDLE_BATCHES = 3;

export type ImportStage =
  | 'preview'
  | 'daily'
  | 'activities'
  | 'fit'
  | 'weather-recent'
  | 'weather-archive'
  | 'finalizing';

export interface ImportProgress {
  stage: ImportStage;
  label: string;
  detail?: string;
  totalActivities?: number;
  existingActivities?: number;
  missingActivities?: number;
  fitDone?: number;
  fitPending?: number;
  fitTotal?: number;
  weatherDone?: number;
  weatherPending?: number;
  weatherTotal?: number;
  weatherWithoutCoordinates?: number;
  batch?: number;
}

export interface ImportSummary {
  preview: GarminImportPreview;
  daily: Record<string, unknown>;
  activities: Record<string, unknown>;
  fit: {
    attempts: number;
    enriched: number;
    errors: number;
    pending: number;
  };
  weatherProcessed: number;
  weatherErrors: number;
  finalStatus: GarminImportStatus;
}

export type GarminImportState =
  | { status: 'idle'; daysBack: null }
  | { status: 'running'; daysBack: number; progress: ImportProgress }
  | { status: 'success'; daysBack: number; summary: ImportSummary; finishedAt: string }
  | { status: 'error'; daysBack: number; error: string; finishedAt: string };

let state: GarminImportState = { status: 'idle', daysBack: null };
let activePromise: Promise<ImportSummary> | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function setState(next: GarminImportState) {
  state = next;
  emit();
}

export function getGarminImportState(): GarminImportState {
  return state;
}

export function subscribeGarminImport(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useGarminImportJob() {
  return useSyncExternalStore(
    subscribeGarminImport,
    getGarminImportState,
    getGarminImportState,
  );
}

export function startGarminImport(daysBack: number): Promise<ImportSummary> {
  if (state.status === 'running' && activePromise) {
    return activePromise;
  }

  activePromise = runPreciseImport(daysBack)
    .then((summary) => {
      setState({
        status: 'success',
        daysBack,
        summary,
        finishedAt: new Date().toISOString(),
      });
      return summary;
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : 'Import impossible.';
      setState({
        status: 'error',
        daysBack,
        error: message,
        finishedAt: new Date().toISOString(),
      });
      throw error;
    })
    .finally(() => {
      activePromise = null;
    });

  return activePromise;
}

export function resetGarminImportResult() {
  if (state.status !== 'running') {
    setState({ status: 'idle', daysBack: null });
  }
}

export function formatImportPeriod(daysBack: number): string {
  return IMPORT_PERIOD_OPTIONS.find((option) => option.value === daysBack)?.label ?? `${daysBack} jours`;
}

export function shortImportPeriod(daysBack: number): string {
  if (daysBack === 365) return '1 an';
  if (daysBack === 730) return '2 ans';
  return `${daysBack}j`;
}

export function estimateImportDurationLabel(daysBack: number): string {
  if (daysBack <= 30) return 'selon le volume trouve';
  if (daysBack <= 90) return 'quelques minutes selon les activites';
  if (daysBack <= 180) return 'souvent 8-20 min';
  if (daysBack <= 365) return 'souvent 15-35 min';
  return 'peut depasser 30 min';
}

function numberFromRecord(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function publishProgress(
  daysBack: number,
  progress: ImportProgress,
  status?: GarminImportStatus,
  preview?: GarminImportPreview,
) {
  const nextProgress: ImportProgress = { ...progress };
  const totalActivities = status?.total_activities ?? preview?.total_activities;
  const existingActivities = preview?.existing_activities;
  const missingActivities = preview?.missing_activities;

  if (totalActivities != null) nextProgress.totalActivities = totalActivities;
  if (existingActivities != null) nextProgress.existingActivities = existingActivities;
  if (missingActivities != null) nextProgress.missingActivities = missingActivities;
  if (status?.fit_done != null) nextProgress.fitDone = status.fit_done;
  if (status?.fit_pending != null) nextProgress.fitPending = status.fit_pending;
  if (status?.fit_total != null) nextProgress.fitTotal = status.fit_total;
  if (status?.weather_done != null) nextProgress.weatherDone = status.weather_done;
  if (status?.weather_pending != null) nextProgress.weatherPending = status.weather_pending;
  if (status?.weather_total != null) nextProgress.weatherTotal = status.weather_total;
  if (status?.weather_without_coordinates != null) {
    nextProgress.weatherWithoutCoordinates = status.weather_without_coordinates;
  }

  setState({
    status: 'running',
    daysBack,
    progress: nextProgress,
  });
}

async function runPreciseImport(daysBack: number): Promise<ImportSummary> {
  publishProgress(daysBack, {
    stage: 'preview',
    label: 'Comptage des activites Garmin',
    detail: formatImportPeriod(daysBack),
  });
  const preview = await agonApi.previewGarminImport(daysBack);

  publishProgress(daysBack, {
    stage: 'activities',
    label: 'Import des activites Garmin',
    detail: `${preview.total_activities} activite(s) trouvee(s), ${preview.missing_activities} nouvelle(s) a creer`,
  }, undefined, preview);
  const activities = await agonApi.syncGarminActivities(daysBack);

  let status = await agonApi.getGarminImportStatus(daysBack);
  const fitResult = await runFitBackfill(daysBack, status, preview);
  status = fitResult.status;

  publishProgress(daysBack, {
    stage: 'daily',
    label: 'Synchronisation Garmin daily',
    detail: `${daysBack} jour(s) de donnees physiologiques`,
  }, status, preview);
  const daily = await agonApi.syncGarminDaily(daysBack);
  status = await agonApi.getGarminImportStatus(daysBack);

  publishProgress(daysBack, {
    stage: 'finalizing',
    label: 'Validation des compteurs',
    detail: `${status.fit_pending} FIT restant(s) · ${status.weather_pending} meteo restant(s)`,
  }, status, preview);

  return {
    preview,
    daily,
    activities,
    fit: fitResult.summary,
    weatherProcessed: 0,
    weatherErrors: 0,
    finalStatus: status,
  };
}

async function runFitBackfill(
  daysBack: number,
  initialStatus: GarminImportStatus,
  preview: GarminImportPreview,
): Promise<{
  summary: ImportSummary['fit'];
  status: GarminImportStatus;
}> {
  let status = initialStatus;
  let attempts = 0;
  let enriched = 0;
  let errors = 0;
  let idleBatches = 0;

  while (status.fit_pending > 0) {
    const beforePending = status.fit_pending;
    publishProgress(daysBack, {
      stage: 'fit',
      label: 'Enrichissement FIT activite par activite',
      detail: `Activite ${status.fit_done + 1}/${status.fit_total}`,
    }, status, preview);

    const result = await agonApi.enrichGarminFit(FIT_BATCH_SIZE);
    const resultRecord = result as Record<string, unknown>;
    attempts += numberFromRecord(resultRecord, 'total');
    enriched += numberFromRecord(resultRecord, 'enriched');
    errors += numberFromRecord(resultRecord, 'errors');

    status = await agonApi.getGarminImportStatus(daysBack);
    publishProgress(daysBack, {
      stage: 'fit',
      label: 'Enrichissement FIT activite par activite',
      detail: `${status.fit_done}/${status.fit_total} termine(s), ${status.fit_pending} restant(s)`,
    }, status, preview);

    if (status.fit_pending >= beforePending && numberFromRecord(resultRecord, 'enriched') === 0) {
      idleBatches += 1;
      if (idleBatches >= MAX_IDLE_BATCHES) break;
    } else {
      idleBatches = 0;
    }
  }

  return {
    summary: {
      attempts,
      enriched,
      errors,
      pending: status.fit_pending,
    },
    status,
  };
}
