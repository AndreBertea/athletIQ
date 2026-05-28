/**
 * Calcul du score readiness.
 *
 * ───────────────────────────────────────────────────────────────────────
 *  POURQUOI sRPE EST EXCLU DU SCORE COMPOSITE
 * ───────────────────────────────────────────────────────────────────────
 *
 * Décision figée et documentée dans la doc démarche du projet.
 *
 * Le score readiness mesure l'état du système au réveil ; le sRPE mesure
 * la charge appliquée la veille. Les intégrer dans une même moyenne
 * pondérée pénaliserait un athlète qui s'entraîne — un athlète sortant
 * d'une grosse séance avec wellness intact 4/4/4/4 doit recevoir un
 * signal positif (bonne tolérance), pas un score amoindri.
 *
 * Cohérent avec le rejet de l'ACWR (Impellizzeri 2020/2021), qui était
 * précisément l'instrument combinant charge et état pour la prédiction
 * de blessure — démarche disqualifiée sur le plan scientifique.
 *
 * Le sRPE reste capté à chaque check-in (Q5) parce qu'il est indispensable
 * pour :
 *   1. l'insight textuel matinal (causalité explicite, cf. insights.ts),
 *   2. le monotony index hebdomadaire (Foster 1998),
 *   3. les règles d'alerte coach (vue `readiness_alerts`, V2).
 *
 * ───────────────────────────────────────────────────────────────────────
 *  FORMULE
 * ───────────────────────────────────────────────────────────────────────
 *
 *   score_raw     = mean(wellbeing, sleep_quality, legs, motivation) × 20
 *   score_z       = (score_raw - baseline.score_mean_28d) / baseline.score_sd_28d
 *   display_score = round(score_raw)             # 0–100
 *   display_delta = round(score_raw - baseline.score_mean_28d)
 *   display_color = green   si |score_z| < 0.5
 *                   orange  si 0.5 ≤ |score_z| < 1.5
 *                   rouge   si       |score_z| ≥ 1.5
 *
 * Échelle linéaire 1–5 → 20–100 (1×20 = 20, 5×20 = 100). Poids égaux.
 * 4 items wellness uniquement.
 *
 * ───────────────────────────────────────────────────────────────────────
 *  GATING J14 (CALIBRATION)
 * ───────────────────────────────────────────────────────────────────────
 *
 * Si baseline.days_recorded < 14 (Saw 2017, ≥14 j pour première variance
 * utile) :
 *   - calibrated = false
 *   - score, zScore, delta = null      (jamais affichés)
 *   - color = 'green' par défaut       (pas de pastille z)
 *   - dimensions[i].z = null           (l'UI affiche valeurs brutes 1–5)
 *   - insight = template descriptif   (jamais comparatif)
 *
 * Le composant Home doit alors monter <CalibrationBar> + <DimensionStrip
 * showZ={false} /> + <InsightCard> avec le insight descriptif.
 */

import type {
  BaselineRow,
  ReadinessEntry,
  ScoreResult,
} from '@/types/domain';
import {
  buildDimensionScores,
  daysRecorded,
  isCalibrated,
  scoreStats,
} from './baseline';
import {
  buildCalibrationInsightDescriptor,
  buildStableInsightDescriptor,
} from './insights';
import { zColor, zScore } from './zscore';

/**
 * Construit le ScoreResult consolidé pour une entrée du jour donnée.
 *
 * @param entry - Entrée du jour (ou null si pas encore saisie ; on retombe
 *                alors sur un résultat "neutre" qui permet à l'UI Home de
 *                rendre malgré tout — cas atypique, mais évite les crashes).
 * @param baseline - Vue `readiness_baseline` du user (peut être null si la
 *                   table est encore vide).
 *
 * Le résultat est mémoïsable côté hook (les inputs sont tous primitifs ou
 * références stables).
 */
export function computeScore(
  entry: ReadinessEntry | null | undefined,
  baseline: BaselineRow | null | undefined,
): ScoreResult {
  const calibrated = isCalibrated(baseline);
  const days = daysRecorded(baseline);

  // Pas d'entrée du jour : on renvoie une coquille vide, exploitable mais
  // sans payload. Home redirigera de toute façon vers /checkin.
  if (!entry) {
    return {
      calibrated,
      daysRecorded: days,
      score: null,
      delta: null,
      zScore: null,
      color: 'green',
      dimensions: [],
      insight: null,
    };
  }

  // 1. score brut sur les 4 dimensions wellness (sRPE EXCLU, cf. en-tête).
  const meanRaw =
    (entry.wellbeing +
      entry.sleep_quality +
      entry.legs +
      entry.motivation) /
    4;
  const scoreRaw = meanRaw * 20;

  // 2. décomposition par dimension (z + couleur si calibré).
  const dimensions = buildDimensionScores(
    {
      wellbeing: entry.wellbeing,
      sleep_quality: entry.sleep_quality,
      legs: entry.legs,
      motivation: entry.motivation,
    },
    baseline,
    calibrated,
  );

  // 3. branche calibration : pas de score, pas de z, insight descriptif.
  if (!calibrated) {
    return {
      calibrated: false,
      daysRecorded: days,
      score: null,
      delta: null,
      zScore: null,
      color: 'green',
      dimensions,
      insight: buildCalibrationInsightDescriptor(dimensions),
    };
  }

  // 4. branche stable : z global + couleur + delta vs baseline mean.
  const stats = scoreStats(baseline);
  const zGlobal = zScore(scoreRaw, stats.mean, stats.sd);
  const colorGlobal = zColor(zGlobal);
  const delta =
    stats.mean !== null && Number.isFinite(stats.mean)
      ? Math.round(scoreRaw - stats.mean)
      : null;

  return {
    calibrated: true,
    daysRecorded: days,
    score: Math.round(scoreRaw),
    delta,
    zScore: zGlobal,
    color: colorGlobal,
    dimensions,
    insight: buildStableInsightDescriptor({
      dimensions,
      srpeYesterday: entry.srpe_yesterday,
    }),
  };
}
