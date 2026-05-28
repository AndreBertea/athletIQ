/**
 * StreakBadge — affichage SOBRE de la consistance.
 *
 * Anti-patterns évités :
 *   ❌ pas de flamme, pas de mascotte, pas de confetti.
 *   ❌ pas de notif culpabilisante.
 *
 * Texte neutre. Si freeze consommé, sous-texte "freeze auto" — pas
 * d'alerte.
 */

import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { useStreak } from '@/hooks/useStreak';
import { cn } from '@/lib/utils';

interface StreakBadgeProps {
  /** Total de saisies effectives sur la période (ex. 23 sur 30). */
  totalEntries?: number;
  /** Total de jours considérés (par défaut 30). */
  windowDays?: number;
  /** Variante visuelle : sur fond signature (header) ou neutre (footer). */
  variant?: 'on-signature' | 'on-surface';
  className?: string;
}

export function StreakBadge({
  totalEntries,
  windowDays = 30,
  variant = 'on-signature',
  className,
}: StreakBadgeProps) {
  const { t } = useTranslation();
  const { streak, isLoading } = useStreak();

  const onSignature = variant === 'on-signature';

  if (isLoading) {
    return (
      <div className={cn('flex items-baseline gap-3', className)}>
        <span
          className={cn(
            'text-xs font-medium tracking-widest uppercase',
            onSignature ? 'text-white/70' : 'text-muted-foreground',
          )}
        >
          {t('history.streak.eyebrow')}
        </span>
        <span
          className={cn(
            'font-display text-xl font-semibold tracking-tight',
            onSignature ? 'text-white/80' : 'text-foreground',
          )}
        >
          —
        </span>
      </div>
    );
  }

  const dayLabel =
    streak.length === 1
      ? t('history.streak.dayOne')
      : t('history.streak.dayMany');
  const subtext = buildSubtext(t, {
    streakLength: streak.length,
    frozenDays: streak.frozenDays,
    freezeAvailable: streak.freezeAvailable,
    totalEntries,
    windowDays,
  });

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-baseline gap-3">
        <span
          className={cn(
            'text-xs font-medium tracking-widest uppercase',
            onSignature ? 'text-white/70' : 'text-muted-foreground',
          )}
        >
          {t('history.streak.eyebrow')}
        </span>
      </div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span
          className={cn(
            'font-display text-2xl font-semibold tracking-tight',
            onSignature ? 'text-white' : 'text-foreground',
          )}
        >
          {streak.length} {dayLabel}
        </span>
        {subtext ? (
          <span
            className={cn(
              'text-xs',
              onSignature ? 'text-white/70' : 'text-muted-foreground',
            )}
          >
            {subtext}
          </span>
        ) : null}
      </div>
    </div>
  );
}

interface SubtextArgs {
  streakLength: number;
  frozenDays: number;
  freezeAvailable: boolean;
  totalEntries: number | undefined;
  windowDays: number;
}

function buildSubtext(
  t: TFunction<'translation', undefined>,
  {
    streakLength,
    frozenDays,
    freezeAvailable,
    totalEntries,
    windowDays,
  }: SubtextArgs,
): string | null {
  if (streakLength === 0) {
    return t('history.streak.subtextEmpty');
  }
  if (totalEntries != null) {
    const freezeBit =
      frozenDays > 0
        ? t('history.streak.freezeAuto', { count: frozenDays })
        : freezeAvailable
          ? t('history.streak.freezeAvailable')
          : '';
    return t('history.streak.subtextEntries', {
      count: totalEntries,
      window: windowDays,
      freezeBit,
    });
  }
  if (frozenDays > 0) {
    return t('history.streak.freezeAutoOnly', { count: frozenDays });
  }
  if (freezeAvailable) {
    return t('history.streak.freezeAvailableOnly');
  }
  return null;
}

export default StreakBadge;
