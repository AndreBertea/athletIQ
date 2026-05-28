/**
 * i18n setup — Enduraw Readiness (FR par défaut, EN secondaire).
 *
 * Architecture extensible : ajouter une langue = dropper un nouveau JSON
 * dans `locales/`, l'importer ici, l'ajouter à `SUPPORTED_LANGUAGES` et
 * au record `resources`. Aucun changement requis dans les composants.
 *
 * Détection :
 *   1. localStorage `enduraw.lang` — choix explicite de l'utilisateur
 *      (sélecteur de drapeaux sur /auth ou /profile).
 *   2. langue navigateur — fallback automatique à la première visite.
 *   3. fallback final — `fallbackLng: 'fr'`.
 *
 * `escapeValue: false` car React échappe déjà côté DOM.
 */

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import fr from './locales/fr.json';
import en from './locales/en.json';

export const SUPPORTED_LANGUAGES = ['fr', 'en'] as const;
export type Lang = (typeof SUPPORTED_LANGUAGES)[number];

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      fr: { translation: fr },
      en: { translation: en },
    },
    fallbackLng: 'fr',
    supportedLngs: SUPPORTED_LANGUAGES,
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'enduraw.lang',
      caches: ['localStorage'],
    },
  });

export default i18n;
