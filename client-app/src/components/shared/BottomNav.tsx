/**
 * BottomNav — barre de navigation principale pour les routes auth.
 *
 * Source visuelle : `docs/result/claude-design/project/screens.jsx`
 * (composant `BottomNav`, l. 97). Active state via `useLocation()` —
 * pas de prop `active` côté consommateurs, on s'aligne sur l'URL.
 *
 * 3 items AGON :
 *   - Home             → /home
 *   - Live             → /live, /live/shared et /live/:id
 *   - Race Predictor   → /race-predictor
 *
 * Le profil n'est plus dans le footer : il est ouvert depuis la pastille
 * avatar du header. Le check-in est intégré en haut de Home.
 */

import { type ReactElement } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Gauge, Radio } from 'lucide-react';
import { cn } from '@/lib/utils';

interface NavItem {
  to: string;
  /** Libellé direct (fallback si la clé i18n n'existe pas). */
  label: string;
  matchPaths: readonly string[];
  icon: () => ReactElement;
}

const NAV_ITEMS: readonly NavItem[] = [
  {
    to: '/home',
    label: 'Home',
    matchPaths: ['/home', '/checkin', '/activities'],
    icon: HomeIcon,
  },
  {
    to: '/live',
    label: 'Live',
    // matchPaths sert au highlight : /live, /live/shared et /live/:id
    // doivent tous activer l'onglet.
    matchPaths: ['/live'],
    icon: LiveIcon,
  },
  {
    to: '/race-predictor',
    label: 'Predictor',
    matchPaths: ['/race-predictor'],
    icon: PredictorIcon,
  },
];

export function BottomNav() {
  const { t } = useTranslation();
  const location = useLocation();

  return (
    <nav
      className={cn(
        'flex shrink-0',
        'border-border-subtle border-t backdrop-blur-xl',
      )}
      style={{
        // Hauteur = 56px (zone tactile compacte, > 44pt Apple min) +
        // safe-area iOS (~34px sur les iPhones avec home indicator).
        // 90px total au lieu de 106px : footer plus discret, icônes
        // proches du bord physique de l'écran.
        height: 'calc(56px + env(safe-area-inset-bottom))',
        paddingBottom: 'env(safe-area-inset-bottom)',
        // Couleur de base semi-transparente : laisse passer le blur
        // pour voir le contenu défiler dessous (effet verre dépoli).
        // Tokens adaptatifs : glass orange chaud sur dark, ivoire frosted
        // avec halo terra discret en clair (cf. --bottomnav-* design-system).
        backgroundColor: 'var(--bottomnav-bg)',
        backgroundImage: 'var(--bottomnav-image)',
        WebkitBackdropFilter: 'blur(18px) saturate(160%)',
        boxShadow: 'var(--bottomnav-shadow)',
      }}
      aria-label={t('nav.ariaLabel')}
    >
      {NAV_ITEMS.map((item) => {
        const isActive = item.matchPaths.some((p) =>
          location.pathname.startsWith(p),
        );
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={cn(
              'flex flex-1 flex-col items-center justify-end gap-0.5 pb-1.5 transition-colors',
              isActive
                ? 'text-brand-cyan'
                : 'text-muted-foreground hover:text-foreground',
            )}
            aria-current={isActive ? 'page' : undefined}
          >
            <item.icon />
            <span
              className={cn(
                'text-xs',
                isActive
                  ? 'text-foreground font-semibold'
                  : 'text-muted-foreground font-medium',
              )}
            >
              {item.label}
            </span>
          </NavLink>
        );
      })}
    </nav>
  );
}

function HomeIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 9.5L12 3l9 6.5V21a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1V9.5z" />
    </svg>
  );
}

function LiveIcon() {
  // Icone "Radio" de lucide-react, calibrée à 22px pour s'aligner sur les
  // autres icones SVG inline (HomeIcon, UserIcon). On la wrappe pour
  // garder un component arity zéro côté NavItem.
  return <Radio width={22} height={22} strokeWidth={1.5} aria-hidden="true" />;
}

function PredictorIcon() {
  return <Gauge width={22} height={22} strokeWidth={1.5} aria-hidden="true" />;
}

export default BottomNav;
