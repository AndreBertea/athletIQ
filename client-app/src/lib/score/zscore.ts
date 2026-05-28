/**
 * z-score helpers.
 *
 * `dimColor(value, mean, sd)` mappe une valeur brute (1–5 pour une
 * dimension wellness, 0–100 pour le score composite) à une couleur PDS
 * selon la distance à la baseline 28 j.
 *
 *   |z| < 0.5            → green   (dans la norme)
 *   0.5 ≤ |z| < 1.5      → orange  (variation marquée)
 *   |z| ≥ 1.5            → red     (extrême individuel)
 *
 * Pure : pas de dépendance, pas d'effet de bord. Les seuils correspondent
 * au Smallest Worthwhile Change (Buchheit 2014, SWC = 0.5 σ) et à la
 * convention z = ±1.5 σ retenue pour la pastille rouge dans la revue 1.
 *
 * Si la baseline n'est pas calibrée (sd manquant ou nul), on retombe sur
 * `green` par défaut — le composant consommateur ne doit alors PAS afficher
 * la valeur du z (rendu purement neutre côté UI).
 */

import type { ZColor } from '@/types/domain';

/** Calcule un z-score. Retourne null si la baseline n'est pas exploitable. */
export function zScore(
  value: number,
  mean: number | null,
  sd: number | null,
): number | null {
  if (mean === null || sd === null) return null;
  if (!Number.isFinite(mean) || !Number.isFinite(sd)) return null;
  if (sd <= 0) return null;
  return (value - mean) / sd;
}

/**
 * Mappe un z-score à une couleur. Si z est null (baseline incomplète),
 * retourne 'green' par défaut — l'UI doit alors masquer la valeur du z.
 */
export function zColor(z: number | null): ZColor {
  if (z === null || !Number.isFinite(z)) return 'green';
  const abs = Math.abs(z);
  if (abs < 0.5) return 'green';
  if (abs < 1.5) return 'orange';
  return 'red';
}

/** Helper composé : value × baseline → couleur directe. */
export function dimColor(
  value: number,
  mean: number | null,
  sd: number | null,
): ZColor {
  return zColor(zScore(value, mean, sd));
}
