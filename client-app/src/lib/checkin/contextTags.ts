/**
 * Catalogue fermé des tags contextuels Q6 (V1).
 * Source de vérité — pas de table SQL associée.
 *
 * Les libellés humains vivent dans les fichiers locales i18n
 * (`web/src/i18n/locales/{fr,en}.json` → `checkin.context.tags.{code}`).
 * Ce fichier ne définit que la structure stable : code (clé BDD) + emoji.
 */

export const CONTEXT_TAGS = [
  { code: 'cold', emoji: '🤧' },
  { code: 'travel', emoji: '✈️' },
  { code: 'alcohol', emoji: '🍷' },
  { code: 'work_stress', emoji: '💼' },
  { code: 'period', emoji: '🩸' },
  { code: 'jetlag', emoji: '🌍' },
  { code: 'low_appetite', emoji: '🍽️' },
  { code: 'injury_doubt', emoji: '🩹' },
  { code: 'race_prep', emoji: '🏁' },
] as const;

export type ContextTag = (typeof CONTEXT_TAGS)[number];
export type ContextTagCode = ContextTag['code'];

export const CONTEXT_TAG_CODES: readonly ContextTagCode[] = CONTEXT_TAGS.map(
  (t) => t.code,
);

export function isContextTagCode(value: string): value is ContextTagCode {
  return (CONTEXT_TAG_CODES as readonly string[]).includes(value);
}
