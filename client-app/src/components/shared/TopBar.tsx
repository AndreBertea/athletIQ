/**
 * TopBar — bandeau superieur sticky pour toutes les routes auth.
 *
 * Adapte AGON :
 *   - Logo : pastille orange + texte "AGON" (au lieu du PNG Enduraw)
 *   - Pastille profil : initiale auto-derivee du user courant (useAuth),
 *     fallback "?" si pas de user. Override possible via prop `initial`.
 *     Si prop `avatarUrl` fournie -> affiche l'image (preparation PDP custom).
 *   - Gradient orange chaud (au lieu du bleu Enduraw).
 *
 * Padding-top utilise `env(safe-area-inset-top)` avec fallback 20px pour
 * coiffer la safe area en PWA installee.
 */

import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/AuthContext';

export const TOPBAR_TOUCH_HEIGHT = 44;
export const TOPBAR_INSET_FALLBACK = 20;

export interface TopBarProps {
  /** Override de l'initiale (sinon auto depuis useAuth().user.displayName). */
  initial?: string;
  /** URL d'une photo de profil custom (sinon affiche l'initiale). */
  avatarUrl?: string;
  /** Titre optionnel affiche a cote du logo ou du bouton retour. */
  title?: string;
  back?: boolean;
  onBack?: () => void;
  dotsActive?: number | null;
  dotsTotal?: number | null;
  hideAvatar?: boolean;
}

export function TopBar({
  initial,
  avatarUrl,
  title,
  back = false,
  onBack,
  dotsActive = null,
  dotsTotal = null,
  hideAvatar = false,
}: TopBarProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { resolvedTheme } = useTheme();
  // Logo wordmark adaptatif : clair = logo sombre sur fond ivoire ;
  // sinon (dark / indéfini au 1er paint) = logo blanc. Fond détouré (PNG transparent).
  const logoSrc =
    resolvedTheme === 'light' ? '/agon-header-light.png' : '/agon-header-dark.png';
  const showDots = dotsTotal != null && dotsTotal > 0;

  // Initiale = override > user.displayName[0] > "?"
  const resolvedInitial =
    initial ??
    (user?.displayName?.charAt(0) ?? user?.fullName?.charAt(0) ?? '?').toUpperCase();

  return (
    <div
      className={cn(
        'flex shrink-0 items-center justify-between',
        'border-b border-border-subtle px-4',
        'backdrop-blur-xl',
      )}
      style={{
        paddingTop: `max(${TOPBAR_INSET_FALLBACK}px, env(safe-area-inset-top))`,
        minHeight: `calc(${TOPBAR_TOUCH_HEIGHT}px + max(${TOPBAR_INSET_FALLBACK}px, env(safe-area-inset-top)))`,
        // Gradient AGON adaptatif (terra→night en dark, terra→ivoire en clair).
        background: 'var(--topbar-bg)',
        WebkitBackdropFilter: 'blur(18px) saturate(160%)',
      }}
    >
      <div className="flex items-center gap-2">
        {back ? (
          <BackButton {...(onBack ? { onBack } : {})} />
        ) : (
          <Link to="/home" className="flex items-center" aria-label="AGON">
            <img src={logoSrc} alt="AGON" className="block h-8 w-auto object-contain" />
          </Link>
        )}
        {title ? (
          <span className="text-[15px] font-semibold text-foreground">{title}</span>
        ) : null}
      </div>

      {showDots && (
        <div className="flex items-center gap-2">
          {Array.from({ length: dotsTotal }).map((_, i) => (
            <span
              key={i}
              className={cn(
                'h-2 rounded-full transition-all',
                i === dotsActive ? 'w-6 bg-brand-cyan' : 'w-2 bg-[var(--active-overlay)]',
              )}
            />
          ))}
        </div>
      )}

      {!showDots && !hideAvatar ? (
        <Link
          to="/profile"
          aria-label={t('topBar.profileLabel')}
          className={cn(
            'flex h-9 w-9 items-center justify-center overflow-hidden rounded-full',
            'bg-[var(--brand-primary)] text-sm font-semibold tracking-wide text-white',
            'shadow-[0_0_0_1px_rgba(255,255,255,0.12),0_4px_12px_rgba(156,73,245,0.35)] transition',
            'hover:brightness-110',
          )}
        >
          {avatarUrl ? (
            <img
              src={avatarUrl}
              alt={user?.displayName ?? 'Profil'}
              className="h-full w-full object-cover"
            />
          ) : (
            <span>{resolvedInitial}</span>
          )}
        </Link>
      ) : null}

      {!showDots && hideAvatar ? <span className="w-9" aria-hidden="true" /> : null}
      {showDots ? <span className="w-9" aria-hidden="true" /> : null}
    </div>
  );
}

interface BackButtonProps {
  onBack?: () => void;
}

function BackButton({ onBack }: BackButtonProps) {
  return (
    <button
      type="button"
      onClick={onBack}
      aria-label="Retour"
      className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--hover-overlay)] text-foreground transition hover:bg-[var(--active-overlay)]"
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="M15 18l-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
