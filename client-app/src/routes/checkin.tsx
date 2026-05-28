/**
 * /checkin — saisie quotidienne (V2 unifié, artboards 05 + 06).
 *
 * Source visuelle : nouveau bundle `screens.jsx`
 *   - 05-checkin (`ScreenCheckinB`) : écran unifié, plus de mode A/B/C.
 *   - 06-context  (`ScreenCheckinC`) : sheet contexte facultative.
 *
 * Layout :
 *   - TopBar visible (logo + avatar profil).
 *   - CheckinHeader : eyebrow date FR + H1 « Comment tu te sens ce matin ? ».
 *   - 4 questions Q1–Q4 (`SegmentedScale` = EmojiGauge dans le bundle).
 *   - Border-top + eyebrow « Ta dernière séance non notée » + carte
 *     `SessionCard` :
 *       · Si une séance est connue (srpe non null ou durée non null),
 *         on l'affiche (durée + RPE accent + slider perception). Ceci
 *         couvre le cas Sophie déjà-saisie (édition) et Thomas pré-rempli.
 *       · Sinon : empty state cliquable « Ajouter ta séance d'hier ».
 *     Plus de toggle séparé : la présence de la carte vaut activation.
 *   - `ContextButtonProminent` plein-largeur, dashed cyan.
 *   - SubmitButton DANS le scroll (pas de sticky / pas de bottomSlot).
 *   - BottomNav VISIBLE en permanence (item « Aujourd'hui » actif).
 *
 * Pré-remplissage : valeurs neutres centrales (3, 3, 3, 3 pour Q1–Q4) si
 * pas d'entrée du jour. Si une entry today existe (Sophie qui revient),
 * on hydrate. Pas de pré-remplissage avec la veille (Saw 2015).
 */

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { Plus, X as XIcon } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { useProfile } from '@/hooks/useProfile';
import {
  CONTEXT_TAG_CODES,
  type ContextTagCode,
} from '@/lib/checkin/contextTags';
import { createPortal } from 'react-dom';
import { Check } from 'lucide-react';
import { SegmentedScale } from '@/components/checkin/SegmentedScale';
import { RpeSlider } from '@/components/checkin/RpeSlider';
import { ContextTagsSheet } from '@/components/checkin/ContextTagsSheet';
import { SubmitButton, type SubmitState } from '@/components/checkin/SubmitButton';
import { AppShell } from '@/components/shared/AppShell';
import { useTodayEntry, todayLocalDate } from '@/hooks/useTodayEntry';
import {
  useSubmitEntry,
  type SubmitEntryPayload,
} from '@/hooks/useSubmitEntry';
import { sportEmoji } from '@/lib/sport';
import { cn } from '@/lib/utils';

// ─── Validation Zod ─────────────────────────────────────────────────────
//
// Schémas créés via factory pour pouvoir injecter le translator courant.

function buildCheckinSchema(t: (key: string) => string) {
  const wellnessScale = z
    .number({ message: t('checkin.errors.scaleValue') })
    .int()
    .min(1)
    .max(5);

  return z.object({
    wellbeing: wellnessScale,
    sleepQuality: wellnessScale,
    legs: wellnessScale,
    motivation: wellnessScale,
    srpeYesterday: z.number().int().min(0).max(10).nullable(),
    sessionDurationMin: z.number().int().min(0).max(999).nullable(),
    contextTags: z
      .array(
        z.enum(
          CONTEXT_TAG_CODES as readonly [ContextTagCode, ...ContextTagCode[]],
        ),
      )
      .max(5, t('checkin.errors.tagsMax')),
  });
}

type CheckinFormState = z.infer<ReturnType<typeof buildCheckinSchema>>;

const NEUTRAL_DEFAULTS: CheckinFormState = {
  wellbeing: 3,
  sleepQuality: 3,
  legs: 3,
  motivation: 3,
  srpeYesterday: null,
  sessionDurationMin: null,
  contextTags: [],
};

// ─── Page ───────────────────────────────────────────────────────────────

export default function CheckinRoute() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const profileQuery = useProfile();

  const todayEntry = useTodayEntry();
  const submitMutation = useSubmitEntry();

  const checkinSchema = useMemo(() => buildCheckinSchema(t), [t]);

  const [form, setForm] = useState<CheckinFormState>(NEUTRAL_DEFAULTS);
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Hydrate form depuis l'entrée du jour si elle existe déjà.
  useEffect(() => {
    const entry = todayEntry.data;
    if (!entry) return;
    setForm({
      wellbeing: entry.wellbeing,
      sleepQuality: entry.sleep_quality,
      legs: entry.legs,
      motivation: entry.motivation,
      srpeYesterday: entry.srpe_yesterday,
      sessionDurationMin: entry.session_duration_min,
      contextTags: [...entry.context_tags],
    });
  }, [todayEntry.data]);

  const todayLabel = useMemo(() => formatTodayLabel(), []);
  const yesterdayLabel = useMemo(() => yesterdayDateLabel(), []);

  const hasSessionYesterday =
    form.srpeYesterday !== null || form.sessionDurationMin !== null;

  const enableSession = () => {
    setForm((f) => ({
      ...f,
      srpeYesterday: f.srpeYesterday ?? 5,
    }));
  };

  const removeSession = () => {
    setForm((f) => ({
      ...f,
      srpeYesterday: null,
      sessionDurationMin: null,
    }));
  };

  const handleSubmit = async () => {
    setErrorMsg(null);
    const parsed = checkinSchema.safeParse(form);
    if (!parsed.success) {
      const firstIssue = parsed.error.issues[0];
      setErrorMsg(firstIssue?.message ?? t('checkin.errors.invalidValues'));
      return;
    }
    setSubmitState('loading');
    const payload: SubmitEntryPayload = {
      wellbeing: parsed.data.wellbeing,
      sleepQuality: parsed.data.sleepQuality,
      legs: parsed.data.legs,
      motivation: parsed.data.motivation,
      srpeYesterday: parsed.data.srpeYesterday,
      sessionDurationMin: parsed.data.sessionDurationMin,
      contextTags: parsed.data.contextTags,
    };
    try {
      await submitMutation.mutateAsync(payload);
      setSubmitState('success');
      // Pattern de vibration plus marqué que le simple `vibrate(20)` du
      // SubmitButton — pulse-pulse signature pour un retour
      // satisfaisant ("c'est validé"). Silencieusement no-op si
      // l'API n'est pas disponible (desktop / Safari sans permission).
      if (typeof navigator.vibrate === 'function') {
        navigator.vibrate([35, 60, 35]);
      }
      // 1100 ms : laisse le temps à l'overlay de pop, animer le check
      // et fade-out avant que la page change. Plus court = saccadé,
      // plus long = ennuyeux.
      // `state.fromCheckin` : signale au RouteDispatcher qu'on vient
      // tout juste de saisir, pour qu'il ne nous renvoie PAS vers
      // /checkin si la query useTodayEntry est encore en train de
      // refetch (race condition entre invalidateQueries et le rerender).
      window.setTimeout(
        () => navigate('/home', { state: { fromCheckin: true } }),
        1100,
      );
    } catch (err) {
      setSubmitState('idle');
      setErrorMsg(
        err instanceof Error
          ? err.message
          : t('checkin.errors.submitFailed'),
      );
    }
  };

  const formDisabled = submitState !== 'idle';
  const userSport = profileQuery.data?.primary_sport ?? 'running';
  const userSportEmoji = sportEmoji(userSport);

  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-md flex-col px-4 pt-4 pb-8">
        <Header label={todayLabel} />

        {/* Q1–Q4 — gauges visuelles */}
        <div className="flex flex-col gap-4">
          <Question label={t('checkin.questions.wellbeing')}>
            <SegmentedScale
              dimension="wellbeing"
              value={form.wellbeing}
              onChange={(v) => setForm((f) => ({ ...f, wellbeing: v }))}
              ariaLabel={t('checkin.ariaLabels.wellbeing')}
              disabled={formDisabled}
            />
          </Question>
          <Question label={t('checkin.questions.sleep')}>
            <SegmentedScale
              dimension="sleep_quality"
              value={form.sleepQuality}
              onChange={(v) => setForm((f) => ({ ...f, sleepQuality: v }))}
              ariaLabel={t('checkin.ariaLabels.sleep')}
              disabled={formDisabled}
            />
          </Question>
          <Question label={t('checkin.questions.legs')}>
            <SegmentedScale
              dimension="legs"
              value={form.legs}
              onChange={(v) => setForm((f) => ({ ...f, legs: v }))}
              ariaLabel={t('checkin.ariaLabels.legs')}
              disabled={formDisabled}
            />
          </Question>
          <Question label={t('checkin.questions.motivation')}>
            <SegmentedScale
              dimension="motivation"
              value={form.motivation}
              onChange={(v) => setForm((f) => ({ ...f, motivation: v }))}
              ariaLabel={t('checkin.ariaLabels.motivation')}
              disabled={formDisabled}
            />
          </Question>
        </div>

        {/* Section séance d'hier */}
        <section className="border-border-subtle mt-6 border-t pt-5">
          <p className="text-eyebrow mb-3">{t('checkin.session.eyebrow')}</p>
          {hasSessionYesterday ? (
            <SessionCard
              srpe={form.srpeYesterday ?? 5}
              durationMin={form.sessionDurationMin}
              yesterdayLabel={yesterdayLabel}
              sportEmoji={userSportEmoji}
              onSrpeChange={(v) =>
                setForm((f) => ({ ...f, srpeYesterday: v }))
              }
              onDurationChange={(v) =>
                setForm((f) => ({ ...f, sessionDurationMin: v }))
              }
              onRemove={removeSession}
              disabled={formDisabled}
            />
          ) : (
            <SessionEmptyState
              onAdd={enableSession}
              disabled={formDisabled}
            />
          )}
        </section>

        {/* Bouton contexte plein-largeur */}
        <div className="mt-4">
          <ContextButton
            tags={form.contextTags}
            onChange={(tags) =>
              setForm((f) => ({ ...f, contextTags: tags }))
            }
            disabled={formDisabled}
          />
        </div>

        {/* Submit button DANS le scroll, BottomNav au-dessous reste visible.
            -mx-4 annule le px-4 du conteneur scroll : le bouton hérite du
            propre px-4 du SubmitButton inline (cf. screens.jsx 05-B). */}
        <div className="-mx-4 mt-4">
          <SubmitButton
            state={submitState}
            onClick={handleSubmit}
            disabled={!userId}
            variant="inline"
          />
        </div>

        {errorMsg ? (
          <p
            role="alert"
            className="text-danger font-text mt-4 text-center text-sm"
          >
            {errorMsg}
          </p>
        ) : null}
      </div>
      <CheckinSuccessOverlay visible={submitState === 'success'} />
    </AppShell>
  );
}

// ─── Overlay de confirmation post-submit ────────────────────────────────

/**
 * Affiche un mini écran "Saisi !" plein viewport pendant ~1100 ms
 * après un submit réussi, avant le `navigate('/home')`. Pop animation
 * sur le cercle + check, fade in du texte, glassmorphism backdrop.
 *
 * Rendu via portail body pour passer au-dessus de TopBar / BottomNav
 * (z-[70] > z-30 du chrome).
 */
function CheckinSuccessOverlay({ visible }: { visible: boolean }) {
  const { t } = useTranslation();
  if (!visible) return null;
  return createPortal(
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'fixed inset-0 z-[70] flex items-center justify-center',
        'bg-background/75 backdrop-blur-md',
        'animate-in fade-in duration-200',
      )}
    >
      <div className="animate-in zoom-in-50 fade-in flex flex-col items-center gap-5 duration-300 ease-out">
        <div
          className={cn(
            'bg-brand-cyan/15 border-brand-cyan flex h-24 w-24 items-center justify-center rounded-full border-2',
            'shadow-glow-cyan',
          )}
        >
          <Check
            className="text-brand-cyan animate-in zoom-in-75 h-12 w-12 duration-500 ease-out"
            strokeWidth={3}
          />
        </div>
        <p className="font-display text-foreground text-2xl font-bold tracking-tight">
          {t('checkin.successOverlay.title')}
        </p>
        <p className="text-muted-foreground font-text text-sm">
          {t('checkin.successOverlay.subtitle')}
        </p>
      </div>
    </div>,
    document.body,
  );
}

// ─── Sous-composants ────────────────────────────────────────────────────

interface HeaderProps {
  label: string;
}

function Header({ label }: HeaderProps) {
  const { t } = useTranslation();
  return (
    <header className="mb-6 flex flex-col gap-1.5">
      <span className="text-eyebrow">{label}</span>
      <h1 className="text-foreground font-text text-2xl leading-tight font-bold tracking-[-0.025em]">
        {t('checkin.title')}
      </h1>
    </header>
  );
}

interface QuestionProps {
  label: string;
  children: React.ReactNode;
}

function Question({ label, children }: QuestionProps) {
  return (
    <section className="flex flex-col gap-2.5">
      <p className="font-text text-foreground text-sm font-medium">
        {label}
      </p>
      {children}
    </section>
  );
}

// ─── Session card (artboard 05 SessionCardCompact-style) ────────────────

interface SessionCardProps {
  srpe: number;
  durationMin: number | null;
  yesterdayLabel: string;
  sportEmoji: string;
  onSrpeChange: (value: number) => void;
  onDurationChange: (value: number | null) => void;
  onRemove: () => void;
  disabled: boolean;
}

function SessionCard({
  srpe,
  durationMin,
  yesterdayLabel,
  sportEmoji,
  onSrpeChange,
  onDurationChange,
  onRemove,
  disabled,
}: SessionCardProps) {
  const { t } = useTranslation();
  return (
    <div
      className={cn(
        'border-border-subtle flex flex-col gap-3 rounded-md border p-4',
      )}
      style={{
        background: 'rgba(15,23,42,0.6)',
        backdropFilter: 'blur(12px)',
        WebkitBackdropFilter: 'blur(12px)',
      }}
    >
      {/* Title row : sport + label + day + remove */}
      <div className="flex items-center gap-2">
        <span aria-hidden className="text-[18px] leading-none">
          {sportEmoji}
        </span>
        <span className="font-text text-foreground text-[15px] font-semibold">
          {t('checkin.session.title')}
        </span>
        <span className="flex-1" />
        <span className="text-muted-foreground font-text text-xs whitespace-nowrap">
          {yesterdayLabel}
        </span>
        <button
          type="button"
          onClick={onRemove}
          disabled={disabled}
          aria-label={t('checkin.session.removeAriaLabel')}
          className={cn(
            'text-muted-foreground hover:text-foreground -mr-1 ml-1 flex h-7 w-7 items-center justify-center rounded-full transition',
            'disabled:cursor-not-allowed disabled:opacity-50',
          )}
        >
          <XIcon size={14} aria-hidden />
        </button>
      </div>

      {/* Metric line : durée affichée pour contexte ; édition dans RpeSlider
          (input numérique discret). RPE accent à droite. */}
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="font-display text-foreground text-[18px] font-bold tracking-[-0.02em] leading-tight whitespace-nowrap">
            {formatDuration(durationMin) ?? '—'}
          </div>
          <div className="text-muted-foreground font-text mt-1 text-[10px] font-medium tracking-[0.06em] uppercase">
            {t('checkin.session.durationLabel')}
          </div>
        </div>
        <div className="text-right min-w-0">
          <div className="font-display text-brand-cyan text-[18px] font-bold tracking-[-0.02em] leading-tight whitespace-nowrap">
            {srpe}/10
          </div>
          <div className="text-muted-foreground font-text mt-1 text-[10px] font-medium tracking-[0.06em] uppercase">
            {t('checkin.session.rpeLabel')}
          </div>
        </div>
      </div>

      {/* Perception (slider 0-10 + input durée optionnel) */}
      <div className="mt-1">
        <p className="text-muted-foreground font-text mb-2 text-[11px] font-medium tracking-[0.06em] uppercase opacity-85">
          {t('checkin.session.perceptionLabel')}
        </p>
        <RpeSlider
          value={srpe}
          onChange={onSrpeChange}
          durationMin={durationMin}
          onDurationChange={onDurationChange}
          disabled={disabled}
          ariaLabel={t('checkin.session.rpeAriaLabel')}
        />
      </div>
    </div>
  );
}

// ─── Empty state séance ─────────────────────────────────────────────────

interface SessionEmptyStateProps {
  onAdd: () => void;
  disabled: boolean;
}

function SessionEmptyState({ onAdd, disabled }: SessionEmptyStateProps) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onAdd}
      disabled={disabled}
      className={cn(
        'border-border-subtle bg-surface-2/40 flex w-full items-center justify-between gap-3 rounded-md border border-dashed p-4 text-left transition',
        'hover:border-border disabled:cursor-not-allowed disabled:opacity-60',
      )}
    >
      <div className="flex flex-col gap-0.5">
        <span className="font-text text-foreground text-sm font-medium">
          {t('checkin.session.addCta')}
        </span>
        <span className="text-muted-foreground font-text text-xs leading-snug">
          {t('checkin.session.addHint')}
        </span>
      </div>
      <Plus size={18} className="text-brand-cyan shrink-0" aria-hidden />
    </button>
  );
}

// ─── Bouton contexte plein-largeur (artboard 05 ContextButtonProminent) ──

interface ContextButtonProps {
  tags: readonly ContextTagCode[];
  onChange: (tags: ContextTagCode[]) => void;
  disabled: boolean;
}

function ContextButton({ tags, onChange, disabled }: ContextButtonProps) {
  const { t } = useTranslation();
  const count = tags.length;
  const ctaLabel =
    count === 0
      ? t('checkin.context.ctaEmpty')
      : count === 1
        ? t('checkin.context.ctaOne')
        : t('checkin.context.ctaMany', { count });
  return (
    <ContextTagsSheet
      value={tags}
      onConfirm={onChange}
      trigger={(open) => (
        <button
          type="button"
          onClick={open}
          disabled={disabled}
          className={cn(
            'border-brand-cyan text-brand-cyan flex h-12 w-full items-center justify-center gap-2.5 rounded-full border border-dashed transition',
            count > 0
              ? 'bg-brand-cyan/15'
              : 'bg-brand-cyan/[0.08] hover:bg-brand-cyan/15',
            'disabled:cursor-not-allowed disabled:opacity-60',
            'font-text text-sm font-semibold',
          )}
        >
          <Plus size={18} aria-hidden />
          <span>{ctaLabel}</span>
        </button>
      )}
    />
  );
}

// ─── Helpers date / format ──────────────────────────────────────────────

const WEEKDAY_FR: readonly string[] = [
  'Dimanche',
  'Lundi',
  'Mardi',
  'Mercredi',
  'Jeudi',
  'Vendredi',
  'Samedi',
];

const WEEKDAY_FR_SHORT: readonly string[] = [
  'dim.',
  'lun.',
  'mar.',
  'mer.',
  'jeu.',
  'ven.',
  'sam.',
];

const MONTH_FR: readonly string[] = [
  'janvier',
  'février',
  'mars',
  'avril',
  'mai',
  'juin',
  'juillet',
  'août',
  'septembre',
  'octobre',
  'novembre',
  'décembre',
];

function formatTodayLabel(now: Date = new Date()): string {
  const day = now.getDate();
  const weekday = WEEKDAY_FR[now.getDay()] ?? '';
  const month = MONTH_FR[now.getMonth()] ?? '';
  // todayLocalDate utilisé pour cohérence éventuelle si besoin debug.
  void todayLocalDate(now);
  return `${weekday} ${day} ${month}`;
}

const MONTH_FR_SHORT: readonly string[] = [
  'janv.',
  'févr.',
  'mars',
  'avr.',
  'mai',
  'juin',
  'juil.',
  'août',
  'sept.',
  'oct.',
  'nov.',
  'déc.',
];

function yesterdayDateLabel(now: Date = new Date()): string {
  const d = new Date(now);
  d.setDate(d.getDate() - 1);
  const weekday = WEEKDAY_FR_SHORT[d.getDay()] ?? '';
  const day = d.getDate();
  const month = MONTH_FR_SHORT[d.getMonth()] ?? '';
  return `${weekday} ${day} ${month}`;
}

/** Convertit minutes en `1h05` / `45 min`. Renvoie null si pas de durée. */
function formatDuration(minutes: number | null): string | null {
  if (minutes === null || minutes <= 0) return null;
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (m === 0) return `${h}h`;
  return `${h}h${m.toString().padStart(2, '0')}`;
}
