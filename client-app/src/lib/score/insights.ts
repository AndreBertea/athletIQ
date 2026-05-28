/**
 * Insights textuels post-saisie.
 *
 * Templates fermés FR/EN. Pas
 * d'IA libre en V1, pas de phrase générique creuse type "Continue
 * comme ça !" (anti-pattern revue 2 — Niemiec & Ryan 2009 sur la
 * motivation autonome).
 *
 * Deux modes :
 *   - Calibration (J<14) : insight purement DESCRIPTIF, jamais comparatif,
 *     basé sur la valeur la plus basse en absolu. Aucun z-score mentionné.
 *   - Stable (J≥14) : insight COMPARATIF basé sur les z-scores < −1.5 σ
 *     (Saw 2017, seuil de variation marquée individuelle).
 *
 * Le sRPE de la veille (Q5) entre dans la phrase quand il vaut ≥ 7 et que
 * la lecture est par ailleurs neutre3 (sRPE est
 * EXCLU du score mais alimente l'insight pour donner une lecture causale).
 *
 * i18n :
 *   - Les builders retournent un descripteur `InsightDescriptor`
 *     (`{ key, vars }`). Le composant qui rend (`InsightCard`,
 *     `useReadinessScore`) appelle `t(key, vars)` avec
 *     `react-i18next`. Cela évite de figer la langue côté lib pure.
 */

import type { DimensionKey, DimensionScore } from '@/types/domain';

/**
 * Descripteur d'insight i18n-ready. `dimKeys` cite les `DimensionKey` à
 * relayer au t() ; le composant les transformera en libellés localisés
 * via `home.dimensionLabels.<key>` (à exposer côté UI), ce qui évite de
 * placer un libellé FR statique dans le payload.
 */
export interface InsightDescriptor {
  key: string;
  vars: Record<string, string | number>;
  /** Clés de dimension à passer en interpolation. Le composant doit
   *  les traduire via i18n avant l'appel `t()`. */
  dimKeys?: Partial<{
    dim: DimensionKey;
    a: DimensionKey;
    b: DimensionKey;
  }>;
}

interface InsightInputs {
  /** Décomposition par dimension issue de buildDimensionScores(). */
  dimensions: DimensionScore[];
  /** sRPE de la veille (0–10), null si pas de séance. */
  srpeYesterday: number | null;
}

/**
 * Insight comparatif (J≥14). Signé par le z-score, pas par la valeur brute.
 *
 *   1. Tous |z| < 0.5  →  "stableAllWithin"
 *   2. 1 dim z < −1.5  →  "stableOneLow" + dim
 *   3. ≥2 dims z<-1.5  →  "stableTwoLows" + a, b
 *   4. sRPE veille ≥7  →  "stableHighSrpe" + srpe
 *   5. fallback        →  "saved"
 */
export function buildStableInsightDescriptor(
  inputs: InsightInputs,
): InsightDescriptor {
  const { dimensions, srpeYesterday } = inputs;

  // Si on n'a aucun z exploitable (cas de bord : baseline pile à 14 jours
  // mais sd = 0 sur une dimension), retombe sur le fallback minimal.
  const withZ = dimensions.filter(
    (d) => d.z !== null && Number.isFinite(d.z),
  );

  if (withZ.length === 0) return { key: 'home.insights.saved', vars: {} };

  // Règle 1 — toutes dimensions dans ±0.5 σ.
  const allWithin = withZ.every((d) => Math.abs(d.z as number) < 0.5);
  if (allWithin) return { key: 'home.insights.stableAllWithin', vars: {} };

  // Trie les dimensions sous la baseline par z croissant (la plus basse d'abord).
  const lows = withZ
    .filter((d) => (d.z as number) < -1.5)
    .sort((a, b) => (a.z as number) - (b.z as number));

  // Règle 3 — au moins 2 dimensions nettement basses.
  if (lows.length >= 2) {
    return {
      key: 'home.insights.stableTwoLows',
      vars: {},
      dimKeys: {
        a: lows[0]!.key,
        b: lows[1]!.key,
      },
    };
  }

  // Règle 2 — exactement 1 dimension nettement basse.
  if (lows.length === 1) {
    return {
      key: 'home.insights.stableOneLow',
      vars: {},
      dimKeys: { dim: lows[0]!.key },
    };
  }

  // Règle 4 — sRPE élevé hier, lecture par ailleurs proche de la baseline.
  if (typeof srpeYesterday === 'number' && srpeYesterday >= 7) {
    return {
      key: 'home.insights.stableHighSrpe',
      vars: { srpe: srpeYesterday },
    };
  }

  // Fallback — il y a des écarts modérés (orange) mais rien de marqué.
  return { key: 'home.insights.saved', vars: {} };
}

/**
 * Insight descriptif (J<14). Strictement non-comparatif (aucun z, aucune
 * référence à une moyenne)2 et §13.6.
 *
 *   - Si une dimension est à 1 ou 2/5, on la signale en valeur absolue
 *     ("Ton sommeil est à 2/5").
 *   - Si plusieurs sont à ≤2, on prend la plus basse, signe le plus net.
 *   - Sinon, message neutre encourageant la consistance, jamais le streak.
 */
export function buildCalibrationInsightDescriptor(
  dimensions: DimensionScore[],
): InsightDescriptor {
  const lows = dimensions
    .filter((d) => d.value <= 2)
    .sort((a, b) => a.value - b.value);

  const lowest = lows[0];
  if (lowest) {
    return {
      key: 'home.insights.calibrationLowest',
      vars: { value: lowest.value },
      dimKeys: { dim: lowest.key },
    };
  }

  return { key: 'home.insights.calibrationDefault', vars: {} };
}
