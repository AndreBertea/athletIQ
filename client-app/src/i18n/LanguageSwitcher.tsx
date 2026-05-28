/**
 * LanguageSwitcher — sélecteur de langue par drapeaux 🇫🇷 🇬🇧.
 *
 * Réutilisé sur :
 *   - `/` (auth) — top-right discret au-dessus du Header
 *   - `/profile` — section "Langue" en haut
 *
 * Signature simple : pas de prop `value` ni `onChange`, on lit/écrit
 * directement via `i18n.changeLanguage()`. La persistance localStorage est
 * gérée par i18next-browser-languagedetector (`caches: ['localStorage']`,
 * clé `enduraw.lang`).
 */

import { useTranslation } from 'react-i18next';
import { SUPPORTED_LANGUAGES, type Lang } from '@/i18n';
import { cn } from '@/lib/utils';

const FLAGS: Record<Lang, string> = {
  fr: '🇫🇷',
  en: '🇬🇧',
};

const LABELS: Record<Lang, string> = {
  fr: 'Français',
  en: 'English',
};

export interface LanguageSwitcherProps {
  className?: string;
  /** Taille des boutons. `sm` (default) = 28px, `md` = 32px. */
  size?: 'sm' | 'md';
}

export function LanguageSwitcher({
  className,
  size = 'sm',
}: LanguageSwitcherProps) {
  const { i18n } = useTranslation();
  const current = (i18n.resolvedLanguage ?? 'fr') as Lang;

  const dim = size === 'sm' ? 'h-7 w-7 text-sm' : 'h-9 w-9 text-base';

  return (
    <div className={cn('flex items-center gap-1', className)} role="group" aria-label="Language">
      {SUPPORTED_LANGUAGES.map((lang) => {
        const active = current === lang;
        return (
          <button
            key={lang}
            type="button"
            onClick={() => {
              void i18n.changeLanguage(lang);
            }}
            aria-pressed={active}
            aria-label={LABELS[lang]}
            className={cn(
              'flex items-center justify-center rounded-full transition',
              'leading-none',
              dim,
              active
                ? 'bg-brand-cyan/15 ring-1 ring-brand-cyan opacity-100'
                : 'opacity-50 hover:opacity-100',
            )}
          >
            <span aria-hidden="true">{FLAGS[lang]}</span>
          </button>
        );
      })}
    </div>
  );
}

export default LanguageSwitcher;
