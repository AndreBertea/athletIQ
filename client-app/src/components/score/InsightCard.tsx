/**
 * InsightCard — carte glassmorphism affichant l'insight du jour.
 *
 * Surface glass (`bg-overlay + backdrop-blur`) avec eyebrow + corps de
 * texte. Le texte est généré côté logique par `lib/score/insights.ts`
 * (templates fermés FR).
 *
 * Eyebrow par défaut "Insight du jour" — surchargeable pour les vues
 * coach ou hebdo (artboard 08).
 */

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

interface InsightCardProps {
  children: ReactNode;
  eyebrow?: string;
  className?: string;
}

export function InsightCard({
  children,
  eyebrow,
  className,
}: InsightCardProps) {
  const { t } = useTranslation();
  const finalEyebrow = eyebrow ?? t('home.insightCard.defaultEyebrow');
  return (
    <div
      className={cn(
        'glass shadow-glow-primary rounded-lg p-5',
        className,
      )}
    >
      <p className="text-eyebrow mb-2">{finalEyebrow}</p>
      <p className="text-foreground text-base font-medium leading-relaxed">
        {children}
      </p>
    </div>
  );
}
