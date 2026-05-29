import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, MapPinned, Plus, Radio, Trash2, Users } from 'lucide-react';
import { liveService, type LiveSession } from '@/lib/api/live';
import { AppShell } from '@/components/shared/AppShell';
import {
  readLiveMultiSessionIds,
  removeLiveMultiSessionId,
  toggleLiveMultiSessionId,
  writeLiveMultiSessionIds,
} from '@/lib/live-multi-selection';
import { cn } from '@/lib/utils';

export default function LiveRoute() {
  return (
    <AppShell>
      <LiveContent />
    </AppShell>
  );
}

export function LiveContent() {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState('');
  const [label, setLabel] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [multiSessionIds, setMultiSessionIds] = useState(readLiveMultiSessionIds);

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['live', 'sessions'],
    queryFn: () => liveService.listSessions(),
    refetchInterval: 5_000,
  });

  const createMutation = useMutation({
    mutationFn: () => liveService.createSession(url, label || undefined),
    onSuccess: () => {
      setUrl('');
      setLabel('');
      setError(null);
      setFormOpen(false);
      queryClient.invalidateQueries({ queryKey: ['live', 'sessions'] });
    },
    onError: (mutationError: unknown) => {
      setError(errorMessage(mutationError, 'Erreur lors de la création'));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => liveService.deleteSession(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['live', 'sessions'] }),
  });

  const multiSessionSet = useMemo(() => new Set(multiSessionIds), [multiSessionIds]);
  const multiSessions = useMemo(
    () =>
      multiSessionIds
        .map((id) => sessions.find((session) => session.id === id))
        .filter((session): session is LiveSession => Boolean(session)),
    [multiSessionIds, sessions],
  );

  const updateMultiSessionIds = (ids: string[]) => {
    setMultiSessionIds(writeLiveMultiSessionIds(ids));
  };

  const toggleMultiSession = (id: string) => {
    updateMultiSessionIds(toggleLiveMultiSessionId(multiSessionIds, id));
  };

  const removeMultiSession = (id: string) => {
    updateMultiSessionIds(removeLiveMultiSessionId(multiSessionIds, id));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!url.trim()) {
      setError('Colle une URL LiveTrack Garmin');
      return;
    }
    createMutation.mutate();
  };

  return (
    <div className="px-4 pb-6 pt-3.5">
      <header className="mb-4 flex items-end justify-between gap-4">
        <div>
          <span className="text-eyebrow mb-1 block">Garmin LiveTrack</span>
          <h1 className="font-display text-[26px] font-extrabold leading-none tracking-tight text-foreground">
            Live
          </h1>
        </div>
        <button
          type="button"
          onClick={() => {
            setFormOpen((open) => !open);
            setError(null);
          }}
          aria-label={formOpen ? 'Fermer le formulaire' : 'Suivre une nouvelle session'}
          className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition',
            formOpen
              ? 'border-border-subtle bg-surface-2 text-foreground'
              : 'border-transparent bg-brand-primary text-white shadow-[var(--glow-primary)]',
          )}
        >
          <Plus className={cn('h-5 w-5 transition-transform', formOpen && 'rotate-45')} />
        </button>
      </header>

      {formOpen ? (
        <section className="mb-3.5 rounded-md border border-border-subtle bg-card p-3.5">
          <p className="mb-1 text-sm font-semibold text-foreground">
            Suivre une session
          </p>
          <p className="mb-3 text-xs leading-relaxed text-muted-foreground">
            Active LiveTrack sur ta Garmin → Paramètres → Sécurité → LiveTrack.
            Colle l&apos;URL générée ici.
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-2">
            <input
              className="input font-mono text-xs"
              type="url"
              aria-label="URL LiveTrack"
              placeholder="https://livetrack.garmin.com/session/..."
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
                setError(null);
              }}
            />
            <input
              className="input text-sm"
              type="text"
              aria-label="Label optionnel"
              placeholder="Label (ex. Sortie longue dimanche)"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
            />

            {error ? (
              <div className="flex items-start gap-1.5 rounded-md border border-danger/40 bg-danger-bg px-2.5 py-2">
                <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger-fg" />
                <span className="text-xs leading-relaxed text-danger-fg">{error}</span>
              </div>
            ) : null}

            <button
              type="submit"
              disabled={createMutation.isPending}
              className="btn btn--primary mt-1 h-10 rounded-md px-3.5 text-[13px]"
            >
              <Plus className="h-4 w-4" />
              {createMutation.isPending ? 'Création...' : 'Suivre'}
            </button>
          </form>
        </section>
      ) : null}

      <SectionHeader label={`${sessions.length} session${sessions.length > 1 ? 's' : ''}`} />

      {isLoading ? (
        <SessionSkeleton />
      ) : sessions.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="flex flex-col gap-2">
          {sessions.map((session) => (
            <SessionCard
              key={session.id}
              session={session}
              isInMulti={multiSessionSet.has(session.id)}
              onToggleMulti={() => toggleMultiSession(session.id)}
              deleting={
                deleteMutation.isPending && deleteMutation.variables === session.id
              }
              onDelete={() => {
                removeMultiSession(session.id);
                deleteMutation.mutate(session.id);
              }}
            />
          ))}
        </ul>
      )}

      <SharedLivePanel
        sessions={multiSessions}
        selectedCount={multiSessionIds.length}
        loading={isLoading && multiSessionIds.length > 0}
        onRemove={removeMultiSession}
      />
    </div>
  );
}

function SharedLivePanel({
  sessions,
  selectedCount,
  loading,
  onRemove,
}: {
  sessions: LiveSession[];
  selectedCount: number;
  loading: boolean;
  onRemove: (id: string) => void;
}) {
  return (
    <section className="mt-5 rounded-md border border-border-subtle bg-card px-3.5 py-3">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-brand-cyan" />
          <span className="text-sm font-semibold text-foreground">Multi-athlètes</span>
          {selectedCount > 0 ? (
            <span className="bg-brand-cyan/10 rounded-full px-2 py-0.5 text-[10px] font-semibold text-brand-cyan">
              {selectedCount}
            </span>
          ) : null}
        </div>
        <Link
          to="/live/shared"
          aria-disabled={selectedCount === 0}
          className={cn(
            'btn btn--primary h-[30px] rounded-full px-2.5 text-[11px]',
            selectedCount === 0 && 'pointer-events-none opacity-45',
          )}
        >
          <MapPinned className="h-3 w-3" />
          Carte
        </Link>
      </div>

      {loading ? (
        <div className="flex flex-col gap-1.5">
          <div className="h-8 animate-pulse rounded-md bg-[var(--surface-3)]" />
          <div className="h-8 animate-pulse rounded-md bg-[var(--surface-3)]" />
        </div>
      ) : selectedCount === 0 ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          Ajoute des sessions depuis Mes sessions pour composer ta carte multi-athlètes.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {sessions.map((session, index) => (
            <div
              key={session.id}
              className="flex items-center justify-between gap-3 rounded-md bg-[var(--surface-3)] px-2.5 py-2"
            >
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="h-2 w-2 shrink-0 animate-pulse rounded-full"
                  style={{ background: athleteColor(index) }}
                />
                <span className="truncate text-[13px] font-semibold text-foreground">
                  {session.label || `Session du ${formatDate(session.created_at)}`}
                </span>
              </div>
              <button
                type="button"
                onClick={() => onRemove(session.id)}
                className="shrink-0 rounded-full px-2 py-1 text-[10px] font-semibold text-muted-foreground transition hover:bg-danger-bg hover:text-danger-fg"
              >
                Retirer
              </button>
            </div>
          ))}
          {selectedCount > sessions.length ? (
            <p className="px-1 text-[11px] text-muted-foreground">
              {selectedCount - sessions.length} session(s) indisponible(s).
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}

function SessionCard({
  session,
  isInMulti,
  onToggleMulti,
  deleting,
  onDelete,
}: {
  session: LiveSession;
  isInMulti: boolean;
  onToggleMulti: () => void;
  deleting: boolean;
  onDelete: () => void;
}) {
  const startIso = session.started_at ?? session.created_at;
  const lastIso = session.last_point_at ?? session.ended_at;
  const duration = formatDuration(startIso, lastIso);
  const meta = statusMeta(session.status);

  return (
    <li className="overflow-hidden rounded-md border border-border-subtle bg-card">
      <div className="flex items-center gap-2.5 px-3.5 py-3">
        <Link to={`/live/${session.id}`} className="min-w-0 flex-1 text-left">
          <div className="mb-1 flex min-w-0 items-center gap-2">
            <span className="truncate text-[13px] font-semibold text-foreground">
              {session.label || `Session du ${formatDate(session.created_at)}`}
            </span>
            <span
              className={cn(
                'inline-flex shrink-0 items-center gap-1 text-[10px] font-semibold',
                meta.textClass,
              )}
            >
              {session.status === 'active' ? (
                <span
                  className={cn('h-1.5 w-1.5 animate-pulse rounded-full', meta.dotClass)}
                />
              ) : null}
              {meta.label}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
            <span>{formatDate(startIso)}</span>
            {duration ? <span>· {duration}</span> : null}
            {lastIso ? <span>· {formatTime(lastIso)}</span> : null}
          </div>
        </Link>

        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={onToggleMulti}
            className={cn(
              'flex h-8 items-center gap-1 rounded-md px-2 text-[10px] font-semibold transition',
              isInMulti
                ? 'bg-brand-cyan/10 text-brand-cyan'
                : 'bg-[var(--surface-3)] text-muted-foreground hover:text-foreground',
            )}
          >
            <Users className="h-3.5 w-3.5" />
            {isInMulti ? 'Retirer' : 'Ajouter'}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={deleting}
            aria-label="Supprimer la session"
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition hover:bg-danger-bg hover:text-danger-fg disabled:opacity-40"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </li>
  );
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <span className="text-eyebrow">{label}</span>
    </div>
  );
}

function SessionSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      <div className="h-[58px] animate-pulse rounded-md border border-border-subtle bg-card" />
      <div className="h-[58px] animate-pulse rounded-md border border-border-subtle bg-card" />
      <div className="h-[58px] animate-pulse rounded-md border border-border-subtle bg-card" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-md border border-border-subtle bg-card p-6 text-center">
      <Radio className="mx-auto h-7 w-7 text-muted-foreground" />
      <p className="mt-2 text-[13px] text-muted-foreground">
        Aucune session. Appuie sur + pour en ajouter.
      </p>
    </div>
  );
}

function statusMeta(status: LiveSession['status']): {
  label: string;
  textClass: string;
  dotClass: string;
} {
  if (status === 'active') {
    return {
      label: 'En direct',
      textClass: 'text-success-fg',
      dotClass: 'bg-success',
    };
  }
  if (status === 'stopped') {
    return {
      label: 'Stoppée',
      textClass: 'text-warning-fg',
      dotClass: 'bg-warning',
    };
  }
  return {
    label: 'Terminée',
    textClass: 'text-muted-foreground',
    dotClass: 'bg-muted-foreground',
  };
}

function athleteColor(index: number): string {
  const colors = [
    'var(--brand-sunset)',
    'var(--success-fg)',
    'var(--info)',
    'var(--warning-fg)',
  ];
  return colors[index % colors.length] ?? 'var(--brand-sunset)';
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR');
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDuration(startIso: string | null, endIso: string | null): string | null {
  if (!startIso) return null;
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const minutes = Math.max(0, Math.floor((end - start) / 60_000));
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    return `${hours}h${String(rest).padStart(2, '0')}`;
  }
  return `${minutes} min`;
}

function errorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object') {
    const response = 'response' in error ? error.response : undefined;
    if (response && typeof response === 'object' && 'data' in response) {
      const data = response.data;
      if (data && typeof data === 'object' && 'detail' in data) {
        const detail = data.detail;
        if (typeof detail === 'string') return detail;
      }
    }
    if ('message' in error && typeof error.message === 'string') return error.message;
  }
  return fallback;
}
