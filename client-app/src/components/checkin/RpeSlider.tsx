/**
 * RpeSlider — Q5 du check-in.
 *
 * Slider 0–10 CR-10 (Foster 1998/2001 ; Bourdon 2017) avec 5 ancres
 * verbales : Repos / Très facile / Modéré / Difficile / Maximal.
 * Snap entier (résolution utile pour le sRPE).
 *
 * Champ optionnel `sessionDurationMin` rendu en input numérique discret
 * (mode A · séance veille à noter).
 *
 * Visuel : portage 1:1 du `RpeSliderCompact` (screens.jsx ligne 606)
 * adapté au mode standalone Q5. Tokens via Tailwind/CSS vars.
 *
 * Pointer events natifs (pas de Radix) pour rester drag-friendly mobile
 * sans dépendance supplémentaire.
 */

import { useCallback, useId, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/**
 * Ancres CR-10. Le `key` cible une clé i18n
 * (`checkin.rpe.anchors.<key>`) — le label localisé est résolu côté
 * composant via `t()`.
 */
const ANCHORS = [
  { tick: 0, key: 'rest' },
  { tick: 2, key: 'veryEasy' },
  { tick: 5, key: 'moderate' },
  { tick: 8, key: 'hard' },
  { tick: 10, key: 'maximal' },
] as const;

const TICK_INDEXES = Array.from({ length: 11 }, (_, i) => i);

export interface RpeSliderProps {
  /** Valeur courante 0–10 entière. */
  value: number;
  /** Notification de changement (entier 0–10). */
  onChange: (value: number) => void;
  /** Durée optionnelle de la séance veille (minutes). null = non renseigné. */
  durationMin?: number | null;
  /** Notification de changement durée. */
  onDurationChange?: ((minutes: number | null) => void) | undefined;
  /** Désactive l'interaction. */
  disabled?: boolean;
  /** Libellé accessible. */
  ariaLabel?: string;
}

function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

export function RpeSlider({
  value,
  onChange,
  durationMin = null,
  onDurationChange,
  disabled = false,
  ariaLabel,
}: RpeSliderProps) {
  const { t } = useTranslation();
  const labelId = useId();
  const trackRef = useRef<HTMLDivElement>(null);
  const safeValue = clamp(Math.round(value), 0, 10);
  const pct = (safeValue / 10) * 100;

  const setFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width === 0) return;
      const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
      const next = Math.round(ratio * 10);
      if (next !== safeValue) onChange(next);
    },
    [onChange, safeValue],
  );

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setFromClientX(event.clientX);
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (event.buttons !== 1) return;
    setFromClientX(event.clientX);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (disabled) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowDown') {
      event.preventDefault();
      onChange(clamp(safeValue - 1, 0, 10));
    } else if (event.key === 'ArrowRight' || event.key === 'ArrowUp') {
      event.preventDefault();
      onChange(clamp(safeValue + 1, 0, 10));
    } else if (event.key === 'Home') {
      event.preventDefault();
      onChange(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      onChange(10);
    }
  };

  const handleDurationChange = (raw: string) => {
    if (!onDurationChange) return;
    if (raw === '') {
      onDurationChange(null);
      return;
    }
    const parsed = Number.parseInt(raw, 10);
    if (Number.isNaN(parsed)) return;
    onDurationChange(clamp(parsed, 0, 999));
  };

  return (
    <div className="flex w-full flex-col gap-3">
      <div
        id={labelId}
        className="flex items-baseline justify-center"
        aria-hidden="true"
      >
        <span className="font-display text-foreground text-4xl font-bold tracking-tight tabular-nums">
          {safeValue}
        </span>
        <span className="font-display text-muted-foreground text-base font-medium">
          {' /10'}
        </span>
      </div>

      <div
        ref={trackRef}
        role="slider"
        tabIndex={disabled ? -1 : 0}
        aria-label={ariaLabel ?? t('checkin.rpe.fallbackAriaLabel')}
        aria-valuemin={0}
        aria-valuemax={10}
        aria-valuenow={safeValue}
        aria-disabled={disabled}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onKeyDown={handleKeyDown}
        className={cn(
          'relative h-6 w-full touch-none select-none',
          disabled ? 'cursor-not-allowed' : 'cursor-pointer',
        )}
        style={{ touchAction: 'none' }}
      >
        <div className="bg-surface-2 absolute inset-x-0 top-2 h-2 rounded-full" />
        <div
          className="bg-brand-primary absolute top-2 left-0 h-2 rounded-full"
          style={{ width: `${pct}%` }}
        />
        {TICK_INDEXES.map((i) => (
          <div
            key={i}
            aria-hidden="true"
            className={cn(
              'pointer-events-none absolute top-1 h-4 w-0.5',
              i <= safeValue ? 'bg-foreground/30' : 'bg-foreground/10',
            )}
            style={{ left: `${(i / 10) * 100}%`, transform: 'translateX(-1px)' }}
          />
        ))}
        <div
          aria-hidden="true"
          className="bg-brand-cyan border-background shadow-glow-cyan pointer-events-none absolute top-0 h-6 w-6 rounded-full border-2"
          style={{ left: `${pct}%`, transform: 'translateX(-12px)' }}
        />
      </div>

      <div className="relative h-4">
        {ANCHORS.map((a) => (
          <span
            key={a.tick}
            aria-hidden="true"
            className="text-muted-foreground absolute font-text text-[10px] font-medium tracking-wider uppercase whitespace-nowrap"
            style={{
              left: `${(a.tick / 10) * 100}%`,
              transform: 'translateX(-50%)',
            }}
          >
            {t(`checkin.rpe.anchors.${a.key}`)}
          </span>
        ))}
      </div>

      {onDurationChange ? (
        <label className="mt-2 flex items-center justify-between gap-3">
          <span className="text-muted-foreground font-text text-xs font-medium tracking-wider uppercase">
            {t('checkin.rpe.durationOptional')}
          </span>
          <span className="flex items-center gap-1.5">
            <input
              type="number"
              inputMode="numeric"
              min={0}
              max={999}
              step={5}
              disabled={disabled}
              value={durationMin ?? ''}
              onChange={(e) => handleDurationChange(e.target.value)}
              placeholder="—"
              className={cn(
                'bg-surface-2 border-border-subtle text-foreground font-display h-9 w-20 rounded-sm border px-2 text-right text-sm tabular-nums',
                'focus:border-brand-cyan focus:outline-none',
                'disabled:cursor-not-allowed disabled:opacity-60',
              )}
              aria-label={t('checkin.rpe.durationAriaLabel')}
            />
            <span className="text-muted-foreground font-text text-xs">
              {t('checkin.rpe.durationMin')}
            </span>
          </span>
        </label>
      ) : null}
    </div>
  );
}

export default RpeSlider;
