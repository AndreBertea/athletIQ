/**
 * Route /onboarding — wizard 3 écrans (V2).
 *
 * Source visuelle : nouveaux artboards 02 / 03 / 04 du bundle
 * `docs/result/claude-design/project/screens.jsx` (`ScreenOnboard1`,
 * `ScreenOnboard2`, `ScreenOnboard3`).
 *
 * Le bundle a été simplifié : plus de saisie du prénom (déjà connu via
 * Supabase auth metadata) ; on collecte uniquement le sport principal +
 * l'heure de check-in matinale. Le récap final est remplacé par un
 * teaser visuel des questions à venir.
 *
 *   1. Pitch — H1 + sous-titre + CTA "Commencer"
 *   2. Personnalisation — sport (grid 2×3) + heure check-in matinale
 *   3. Premier check-in — eyebrow "Prêt ?" + teaser blurred + CTA
 *
 * Submit final → upsert profile via useUpdateProfile + navigate('/checkin').
 *
 * Le wizard reste local (state React) — pas de persistance intermédiaire
 * pour limiter les allers-retours BDD.
 *
 * Pas de TopBar : les dots de progression vivent en haut du contenu
 * (pt-4), comme dans le bundle V2.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useProfile } from '@/hooks/useProfile';
import { useUpdateProfile } from '@/hooks/useUpdateProfile';
import { AppShell } from '@/components/shared/AppShell';
import { cn } from '@/lib/utils';
import type { Sport } from '@/types/domain';

interface WizardState {
  step: 0 | 1 | 2;
  /** Multi-sélection : un athlète peut pratiquer plusieurs disciplines.
   *  En BDD on stocke le 1er comme `primary_sport` (V1, sans schéma
   *  multi-valued) ; les autres servent uniquement à teinter l'UX. */
  sports: Sport[];
  notifTime: string;
}

interface SportMeta {
  code: Sport;
  emoji: string;
}

/**
 * Catalogue des sports — `code` (clé BDD) + `emoji`. Le libellé localisé
 * vient de la clé i18n `onboarding.sports.<code>`.
 */
const SPORTS: readonly SportMeta[] = [
  { code: 'hiking', emoji: '🥾' },
  { code: 'running', emoji: '🏃' },
  { code: 'cycling', emoji: '🚴' },
  { code: 'trail', emoji: '🏔️' },
  { code: 'mtb', emoji: '🚵' },
  { code: 'ebike', emoji: '⚡' },
];

export default function OnboardingRoute() {
  const { t } = useTranslation();
  const profileQuery = useProfile();
  const updateProfile = useUpdateProfile();
  const navigate = useNavigate();

  const [state, setState] = useState<WizardState>(() => ({
    step: 0,
    sports: profileQuery.data?.primary_sport
      ? [profileQuery.data.primary_sport as Sport]
      : ['running'],
    notifTime: (profileQuery.data?.notif_local_time ?? '07:30:00').slice(0, 5),
  }));

  const goNext = () => {
    setState((s) => ({
      ...s,
      step: Math.min(2, s.step + 1) as WizardState['step'],
    }));
  };

  const submit = async () => {
    try {
      await updateProfile.mutateAsync({
        patch: {
          // BDD V1 : un seul sport stocké. On prend le premier sélectionné
          // comme primary ; les autres ne sont pas persistés (on garde
          // un design ouvert pour V1.1 si on décide de stocker un array).
          primary_sport: state.sports[0] ?? 'running',
          notif_local_time: `${state.notifTime}:00`,
        },
      });
      navigate('/checkin', { replace: true });
    } catch (err) {
      // Surface l'erreur — sans ça le RouteDispatcher peut boucler vers
      // /onboarding si le profile n'a pas été créé côté Supabase.
      const message =
        err instanceof Error
          ? err.message
          : t('onboarding.errors.saveFailedFallback');
      toast.error(t('onboarding.errors.saveFailed'), {
        description: message,
      });
    }
  };

  return (
    <AppShell hideTopBar hideBottomNav className="bg-signature">
      <div className="mx-auto flex min-h-full w-full max-w-md flex-col">
        <ProgressDots active={state.step} total={3} />

        {state.step === 0 && <Step1Pitch onContinue={goNext} />}

        {state.step === 1 && (
          <Step2Personalization
            sports={state.sports}
            notifTime={state.notifTime}
            onChange={(p) => setState((s) => ({ ...s, ...p }))}
            onContinue={goNext}
          />
        )}

        {state.step === 2 && (
          <Step3FirstCheckin
            onSubmit={submit}
            isPending={updateProfile.isPending}
          />
        )}
      </div>
    </AppShell>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Progression dots
// ────────────────────────────────────────────────────────────────────────

interface ProgressDotsProps {
  active: number;
  total: number;
}

function ProgressDots({ active, total }: ProgressDotsProps) {
  const { t } = useTranslation();
  return (
    <div
      className="flex shrink-0 items-center justify-center gap-2 pt-4"
      role="progressbar"
      aria-valuenow={active + 1}
      aria-valuemin={1}
      aria-valuemax={total}
      aria-label={t('onboarding.progressLabel', {
        current: active + 1,
        total,
      })}
    >
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={cn(
            'h-2 rounded-full transition-all',
            i === active ? 'bg-brand-cyan w-6' : 'w-2 bg-white/20',
          )}
        />
      ))}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Step 1 — Pitch
// ────────────────────────────────────────────────────────────────────────

interface Step1Props {
  onContinue: () => void;
}

function Step1Pitch({ onContinue }: Step1Props) {
  const { t } = useTranslation();
  return (
    <>
      <section className="flex flex-1 flex-col justify-center px-6">
        <h1 className="font-text text-foreground text-[36px] leading-[1.1] font-extrabold tracking-[-0.03em]">
          {t('onboarding.step1.headline')}
        </h1>
        <p className="text-muted-foreground font-text mt-5 max-w-[300px] text-[17px] leading-[1.5]">
          {t('onboarding.step1.subline')}
        </p>
      </section>

      <FooterCta label={t('onboarding.step1.cta')} onClick={onContinue} />
    </>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Step 2 — Personnalisation (sport + heure check-in)
// ────────────────────────────────────────────────────────────────────────

interface Step2Props {
  sports: Sport[];
  notifTime: string;
  onChange: (patch: Partial<WizardState>) => void;
  onContinue: () => void;
}

function Step2Personalization({
  sports,
  notifTime,
  onChange,
  onContinue,
}: Step2Props) {
  const { t } = useTranslation();
  // Multi-sélection : on add/remove le code, sans imposer un minimum
  // dur — le CTA est désactivé tant que la liste est vide.
  const toggleSport = (code: Sport) => {
    onChange({
      sports: sports.includes(code)
        ? sports.filter((s) => s !== code)
        : [...sports, code],
    });
  };

  const canContinue = sports.length > 0;

  return (
    <>
      <section className="flex flex-1 flex-col justify-center gap-6 px-4 py-6">
        <div>
          <Eyebrow>{t('onboarding.step2.sportsEyebrow')}</Eyebrow>
          <p className="text-muted-foreground font-text mt-1 text-xs leading-snug">
            {t('onboarding.step2.sportsHelper')}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {SPORTS.map((s) => (
            <SportCard
              key={s.code}
              meta={s}
              active={sports.includes(s.code)}
              onClick={() => toggleSport(s.code)}
            />
          ))}
        </div>

        <div>
          <Eyebrow>{t('onboarding.step2.timeEyebrow')}</Eyebrow>
          {/* L'heure devient un bloc cliquable explicite : label à
              gauche, sélecteur à droite stylé en pill cyan. Le
              `<input type="time">` natif ouvre le carrousel iOS au
              tap et reste accessible clavier (web). */}
          <label
            htmlFor="onboard-notif-time"
            className={cn(
              'border-border-subtle bg-card mt-3 flex items-center justify-between rounded-md border px-4 py-4',
              'cursor-pointer transition hover:border-border',
            )}
          >
            <div className="flex flex-col gap-0.5">
              <span className="font-text text-foreground text-sm font-semibold">
                {t('onboarding.step2.timeRowLabel')}
              </span>
              <span className="text-muted-foreground font-text text-xs leading-tight">
                {t('onboarding.step2.timeRowHint')}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-muted-foreground font-text text-[11px] uppercase tracking-widest">
                {t('onboarding.step2.timeRowEdit')}
              </span>
              <input
                id="onboard-notif-time"
                type="time"
                value={notifTime}
                onChange={(e) => onChange({ notifTime: e.target.value })}
                aria-label={t('onboarding.step2.timeAriaLabel')}
                className={cn(
                  'font-display text-brand-cyan bg-brand-cyan/10 border-brand-cyan/30 rounded-full border px-3 py-1.5 text-base font-bold tracking-tight',
                  'cursor-pointer focus:outline-none',
                  'appearance-none [&::-webkit-calendar-picker-indicator]:hidden',
                )}
                style={{ colorScheme: 'dark' }}
              />
            </div>
          </label>
        </div>
      </section>

      <FooterCta
        label={t('onboarding.step2.cta')}
        onClick={onContinue}
        disabled={!canContinue}
      />
    </>
  );
}

interface SportCardProps {
  meta: SportMeta;
  active: boolean;
  onClick: () => void;
}

function SportCard({ meta, active, onClick }: SportCardProps) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'flex h-[88px] flex-col justify-between rounded-md border p-3 text-left transition',
        active
          ? 'border-brand-cyan bg-brand-primary/[0.18] shadow-glow-cyan'
          : 'border-border-subtle bg-surface-2 hover:border-border',
      )}
    >
      <span aria-hidden="true" className="text-[28px] leading-none">
        {meta.emoji}
      </span>
      <span
        className={cn(
          'font-text text-foreground text-sm',
          active ? 'font-semibold' : 'font-medium',
        )}
      >
        {t(`onboarding.sports.${meta.code}`)}
      </span>
    </button>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Step 3 — Premier check-in (teaser)
// ────────────────────────────────────────────────────────────────────────

interface Step3Props {
  onSubmit: () => void;
  isPending: boolean;
}

function Step3FirstCheckin({ onSubmit, isPending }: Step3Props) {
  const { t } = useTranslation();
  const TEASER_ROWS = [
    ['😩', '😐', '🙂', '😄', '💪'],
    ['😴', '😪', '🛏️', '🌙', '⭐'],
    ['🪨', '🧱', '🦵', '⚡', '🏃'],
    ['😶', '🙂', '💪', '🔥', '🚀'],
  ] as const;

  return (
    <>
      <section className="flex flex-1 flex-col justify-center gap-8 px-6 pt-8">
        <div>
          <Eyebrow color="cyan">{t('onboarding.step3.eyebrow')}</Eyebrow>
          <h1 className="font-text text-foreground mt-3 text-[32px] leading-[1.1] font-extrabold tracking-[-0.03em]">
            {t('onboarding.step3.headline')}
          </h1>
          <p className="text-muted-foreground font-text mt-4 text-base leading-[1.5]">
            {t('onboarding.step3.subline')}
          </p>
        </div>

        <div
          aria-hidden="true"
          className="pointer-events-none relative select-none opacity-50"
          style={{ filter: 'blur(1.5px) saturate(0.7)' }}
        >
          {TEASER_ROWS.map((row, i) => (
            <div key={i} className="mb-1.5 flex gap-1">
              {row.map((emoji, j) => (
                <span
                  key={j}
                  className={cn(
                    'border-border-subtle flex h-8 flex-1 items-center justify-center rounded-md border text-[13px]',
                  )}
                  style={{ background: 'rgba(13,18,37,0.5)' }}
                >
                  {emoji}
                </span>
              ))}
            </div>
          ))}
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                'linear-gradient(180deg, transparent 0%, rgba(2,6,23,0.85) 100%)',
            }}
          />
        </div>
      </section>

      <FooterCta
        label={
          isPending ? t('onboarding.step3.ctaPending') : t('onboarding.step3.cta')
        }
        onClick={onSubmit}
        disabled={isPending}
      />
    </>
  );
}

// ────────────────────────────────────────────────────────────────────────
// Eyebrow + FooterCta
// ────────────────────────────────────────────────────────────────────────

interface EyebrowProps {
  children: React.ReactNode;
  color?: 'muted' | 'cyan';
}

function Eyebrow({ children, color = 'muted' }: EyebrowProps) {
  return (
    <p
      className={cn(
        'font-text text-[11px] font-medium tracking-[0.12em] uppercase',
        color === 'cyan' ? 'text-brand-cyan' : 'text-muted-foreground',
      )}
    >
      {children}
    </p>
  );
}

interface FooterCtaProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}

function FooterCta({ label, onClick, disabled = false }: FooterCtaProps) {
  // Sticky bottom + glass : le bouton reste TOUJOURS visible au-dessus
  // du fold, peu importe la hauteur du contenu (iPad / iPhone landscape).
  // Safe-area iOS respectée. Le gradient fade évite la coupure brutale
  // entre le contenu scrollable et le footer fixe.
  return (
    <div
      className="sticky bottom-0 z-10 px-4 pt-6 backdrop-blur-md"
      style={{
        paddingBottom: 'calc(env(safe-area-inset-bottom) + 24px)',
        background:
          'linear-gradient(180deg, rgba(2,6,23,0) 0%, rgba(2,6,23,0.78) 28%, rgba(2,6,23,0.92) 100%)',
      }}
    >
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        className={cn(
          'bg-brand-primary text-foreground h-12 w-full rounded-full font-semibold transition',
          'shadow-glow-primary font-text text-sm hover:brightness-110 disabled:opacity-50',
        )}
      >
        {label}
      </button>
    </div>
  );
}
