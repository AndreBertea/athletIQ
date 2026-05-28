/**
 * SegmentedScale — Q1 à Q4 du check-in.
 *
 * Segmented control 1–5 avec emoji par valeur. Bosch 2019 : segmented ≈
 * slider en qualité de mesure ; Funke 2015 : segmented + rapide à saisir.
 *
 * Pré-remplissage neutre central (3) avant J14, baseline personnelle
 * ensuite. Jamais la valeur de la veille.
 *
 * Visuel : 05-B (composant `EmojiGauge`, screens.jsx l. 1057-1079) —
 * gauges 44 px de haut, segments inactifs en saturation réduite (0.6) +
 * opacité 0.45, segment actif avec primary + ring cyan + glow cyan.
 * Pas de chiffre 1-5 visible (l'emoji porte le sens). Tokens via
 * Tailwind/CSS vars, jamais de hex en dur.
 */

import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import type { DimensionKey } from '@/types/domain';
import { cn } from '@/lib/utils';

/**
 * Catalogue des emojis par dimension. Source : screens.jsx ligne 789-792.
 * Ordre indexé sur la valeur (1 → index 0, 5 → index 4).
 */
export const SCALE_EMOJIS: Record<DimensionKey, readonly [string, string, string, string, string]> = {
  wellbeing: ['😩', '😐', '🙂', '😄', '💪'],
  sleep_quality: ['😴', '😪', '🛏️', '🌙', '⭐'],
  legs: ['🪨', '🧱', '🦵', '⚡', '🏃'],
  motivation: ['😶', '🙂', '💪', '🔥', '🚀'],
};

export interface SegmentedScaleProps {
  /** Valeur courante 1–5. */
  value: number;
  /** Notification de changement (entier 1–5). */
  onChange: (value: number) => void;
  /** Détermine la palette d'emojis. */
  dimension: DimensionKey;
  /** Libellé accessible pour le radiogroup. */
  ariaLabel?: string;
  /** Désactive l'interaction (ex. soumission en cours). */
  disabled?: boolean;
}

const SCALE_VALUES = [1, 2, 3, 4, 5] as const;

export function SegmentedScale({
  value,
  onChange,
  dimension,
  ariaLabel,
  disabled = false,
}: SegmentedScaleProps) {
  const { t } = useTranslation();
  const groupId = useId();
  const emojis = SCALE_EMOJIS[dimension];

  return (
    <div
      role="radiogroup"
      aria-label={
        ariaLabel ??
        t('checkin.ariaLabels.scaleFallback', { dimension })
      }
      className="flex w-full gap-1"
    >
      {SCALE_VALUES.map((v, idx) => {
        const active = v === value;
        const emoji = emojis[idx];
        return (
          <button
            key={v}
            type="button"
            role="radio"
            id={`${groupId}-${v}`}
            aria-checked={active}
            aria-label={t('checkin.ariaLabels.scaleValue', {
              value: v,
              emoji,
            })}
            disabled={disabled}
            onClick={() => onChange(v)}
            className={cn(
              'flex h-11 flex-1 items-center justify-center rounded-md border transition-all duration-150 ease-out',
              'disabled:cursor-not-allowed disabled:opacity-60',
              // Microanimation au tap : la case sélectionnée pop
              // légèrement (~6%) pour donner un retour visuel sans
              // surjouer. Les inactives reculent (scale 100) pour
              // accentuer la différence focale.
              active
                ? 'bg-brand-primary border-brand-cyan shadow-glow-cyan scale-[1.06]'
                : 'border-border-subtle hover:border-border scale-100',
              'active:scale-95', // micro-pulse au moment du tap
            )}
            style={
              active
                ? undefined
                : {
                    background: 'rgba(15,23,42,0.55)',
                    opacity: 0.45,
                    filter: 'saturate(0.6)',
                  }
            }
          >
            <span
              className={cn(
                'text-[20px] leading-none transition-transform duration-150 ease-out',
                active ? 'scale-110' : 'scale-100',
              )}
            >
              {emoji}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default SegmentedScale;
