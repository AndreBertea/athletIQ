import {
  Activity,
  Bike,
  Dumbbell,
  Footprints,
  Mountain,
  Trophy,
  Waves,
  type LucideIcon,
} from 'lucide-react';

export interface SportPresentation {
  Icon: LucideIcon;
  label: string;
  toneClass: string;
}

const SPORT_PRESENTATIONS: Array<{
  match: string[];
  presentation: SportPresentation;
}> = [
  {
    match: ['trailrun', 'trail', 'hiking', 'hike', 'rockclimbing'],
    presentation: {
      Icon: Mountain,
      label: 'Trail',
      toneClass: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200',
    },
  },
  {
    match: ['run', 'virtualrun', 'walk'],
    presentation: {
      Icon: Footprints,
      label: 'Course',
      toneClass: 'border-brand-sunset/30 bg-brand-sunset/10 text-brand-cyan',
    },
  },
  {
    match: ['ride', 'bike', 'cycling', 'virtualride', 'mtb', 'ebike'],
    presentation: {
      Icon: Bike,
      label: 'Velo',
      toneClass: 'border-sky-400/25 bg-sky-400/10 text-sky-200',
    },
  },
  {
    match: ['swim'],
    presentation: {
      Icon: Waves,
      label: 'Natation',
      toneClass: 'border-cyan-400/25 bg-cyan-400/10 text-cyan-200',
    },
  },
  {
    match: ['racketsport', 'tennis', 'badminton', 'squash', 'padel'],
    presentation: {
      Icon: Trophy,
      label: 'Raquette',
      toneClass: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
    },
  },
  {
    match: ['weighttraining', 'workout', 'crossfit', 'gym', 'yoga', 'pilates'],
    presentation: {
      Icon: Dumbbell,
      label: 'Renfo',
      toneClass: 'border-violet-400/25 bg-violet-400/10 text-violet-200',
    },
  },
];

export function getSportPresentation(sportType?: string | null): SportPresentation {
  const normalized = normalizeSportType(sportType);
  const found = SPORT_PRESENTATIONS.find(({ match }) =>
    match.some((item) => normalized.includes(item)),
  );

  return found?.presentation ?? {
    Icon: Activity,
    label: sportType || 'Activite',
    toneClass: 'border-border-subtle bg-surface-2 text-brand-cyan',
  };
}

export function formatDistance(meters?: number | null): string {
  if (meters == null || !Number.isFinite(meters) || meters <= 0) return '—';
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

export function formatDuration(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return '—';
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} h`;
  return `${h} h ${String(m).padStart(2, '0')}`;
}

export function formatDateShort(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: 'short',
  });
}

export function formatDateLong(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });
}

export function formatPace(paceMinPerKm?: number | null): string {
  if (paceMinPerKm == null || !Number.isFinite(paceMinPerKm) || paceMinPerKm <= 0) {
    return '—';
  }
  const minutes = Math.floor(paceMinPerKm);
  const seconds = Math.round((paceMinPerKm % 1) * 60);
  return `${minutes}:${String(seconds).padStart(2, '0')}/km`;
}

export function speedToPace(speedMps?: number | null): number | null {
  if (speedMps == null || !Number.isFinite(speedMps) || speedMps <= 0) return null;
  return 1000 / speedMps / 60;
}

function normalizeSportType(value?: string | null): string {
  return String(value ?? '')
    .toLowerCase()
    .replace(/[\s_-]/g, '');
}
