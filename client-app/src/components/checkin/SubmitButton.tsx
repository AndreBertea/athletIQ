/**
 * SubmitButton — bouton de soumission du check-in.
 *
 * 3 états :
 *  - `idle`     : libellé par défaut « Valider mon check-in »
 *  - `loading`  : spinner + libellé désactivé
 *  - `success`  : check vert + microvibration (`navigator.vibrate(20)`)
 *
 * Microinteraction Tiny Habits Shine (Fogg) — sobre, pas de fanfare ni
 * de confetti. La transition vers `/home` est gérée par le parent.
 *
 * Architecture : ce composant est rendu par /checkin via le `bottomSlot`
 * de l'AppShell — pas de sticky positioning ici, le shell gère l'ancrage
 * en bas du viewport (cf. AppShell.tsx).
 */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export type SubmitState = 'idle' | 'loading' | 'success';

export interface SubmitButtonProps {
  state: SubmitState;
  /** Click handler — actif uniquement quand `state === 'idle'`. */
  onClick: () => void;
  /** Surcharge optionnelle du libellé idle. Si null/undefined, on utilise
   *  la traduction `checkin.submit.idle`. */
  label?: string;
  /** Désactive aussi en idle (ex. validation form pas passée). */
  disabled?: boolean;
  /**
   * Variante de placement :
   *   - `pinned` (défaut) : conteneur ancré bas (gradient + safe-area).
   *     Utilisé en `bottomSlot` d'AppShell.
   *   - `inline`           : conteneur transparent, pas de gradient ni de
   *     safe-area. Utilisé quand le bouton vit dans le scroll au-dessus
   *     d'une BottomNav permanente (artboard 05).
   */
  variant?: 'pinned' | 'inline';
}

const SUCCESS_VIBRATE_MS = 20;

export function SubmitButton({
  state,
  onClick,
  label,
  disabled = false,
  variant = 'pinned',
}: SubmitButtonProps) {
  const { t } = useTranslation();
  const idleLabel = label ?? t('checkin.submit.idle');

  // Vibration courte au passage en success (haptique web).
  useEffect(() => {
    if (state !== 'success') return;
    if (typeof navigator === 'undefined') return;
    if (typeof navigator.vibrate !== 'function') return;
    try {
      navigator.vibrate(SUCCESS_VIBRATE_MS);
    } catch {
      // ignore — certains navigateurs throw quand la page n'a pas le focus
    }
  }, [state]);

  const isDisabled = disabled || state !== 'idle';
  const ariaLabel =
    state === 'loading'
      ? t('checkin.submit.ariaLoading')
      : state === 'success'
        ? t('checkin.submit.ariaSuccess')
        : idleLabel;

  const wrapperStyle =
    variant === 'pinned'
      ? {
          background:
            'linear-gradient(180deg, transparent 0%, var(--background) 40%, var(--background) 100%)',
        }
      : undefined;

  return (
    <div
      className={cn(
        'shrink-0',
        variant === 'pinned'
          ? 'pb-safe-bottom px-4 pt-3 pb-4'
          : 'px-4 py-2',
      )}
      style={wrapperStyle}
    >
      <button
        type="button"
        onClick={onClick}
        disabled={isDisabled}
        aria-label={ariaLabel}
        aria-busy={state === 'loading'}
        className={cn(
          'font-text text-foreground relative flex h-12 w-full items-center justify-center gap-2 rounded-full text-sm font-semibold tracking-wide transition',
          state === 'success'
            ? 'bg-success shadow-glow-success'
            : 'bg-brand-primary shadow-glow-primary hover:brightness-110',
          isDisabled && state !== 'success' ? 'cursor-not-allowed opacity-90' : '',
        )}
      >
        {state === 'loading' ? (
          <>
            <Spinner />
            <span>{t('checkin.submit.loading')}</span>
          </>
        ) : state === 'success' ? (
          <>
            <CheckIcon />
            <span>{t('checkin.submit.success')}</span>
          </>
        ) : (
          <span>{idleLabel}</span>
        )}
      </button>
    </div>
  );
}

function Spinner() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        stroke="currentColor"
        strokeOpacity="0.3"
        strokeWidth="2"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-5 w-5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 12l4 4 10-10" />
    </svg>
  );
}

export default SubmitButton;
