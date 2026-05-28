/**
 * useInsightText — résout un `InsightDescriptor` (lib/score/insights.ts)
 * en string localisée.
 *
 * Pourquoi un hook dédié plutôt qu'un appel direct `t(d.key, d.vars)` :
 * les vars `dim` / `a` / `b` ne sont pas des string brutes mais des
 * `DimensionKey` ; il faut les passer à un sous-`t()` (`home.dimensionLabels.<key>`)
 * AVANT l'appel du template principal — d'où la résolution en deux temps
 * encapsulée ici.
 */

import { useTranslation } from 'react-i18next';
import type { DimensionKey, InsightDescriptor } from '@/types/domain';

export function useInsightText(): (
  descriptor: InsightDescriptor | null,
) => string {
  const { t } = useTranslation();

  return (descriptor: InsightDescriptor | null): string => {
    if (!descriptor) return '';
    const vars: Record<string, string | number> = { ...descriptor.vars };
    if (descriptor.dimKeys) {
      const labelOf = (k: DimensionKey): string =>
        t(`home.dimensionLabels.${k}`);
      const cap = (s: string): string =>
        s.length === 0 ? s : s.charAt(0).toUpperCase() + s.slice(1);
      if (descriptor.dimKeys.dim) vars['dim'] = labelOf(descriptor.dimKeys.dim);
      // Premier libellé de la phrase → capitalisé pour rester cohérent
      // avec le rendu FR ("Sommeil et jambes…").
      if (descriptor.dimKeys.a) vars['a'] = cap(labelOf(descriptor.dimKeys.a));
      if (descriptor.dimKeys.b) vars['b'] = labelOf(descriptor.dimKeys.b);
    }
    return t(descriptor.key, vars);
  };
}
