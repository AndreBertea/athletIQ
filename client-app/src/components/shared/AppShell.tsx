/**
 * AppShell — layout fixe pour les routes auth (Home / History / Profile /
 * Checkin / Onboarding).
 *
 * Stack visuel (du fond vers le dessus) :
 *   1. `.bg-signature` — gradient radial cyan→bleu→noir centré en bas,
 *      visible sur TOUTES les pages, y compris onboarding (demande client).
 *   2. `<main>` scrollable, couvre tout le viewport. Padding-top et
 *      padding-bottom calculés pour que le contenu ne soit pas masqué
 *      par les barres mais puisse bien défiler DERRIÈRE elles (effet
 *      glass).
 *   3. TopBar et BottomNav en `position: absolute`, z-index 30. Leur
 *      `backdrop-blur-xl` floute le contenu qui défile dessous → effet
 *      verre dépoli demandé par le client.
 *
 * Pourquoi `position: absolute` plutôt que flex-column comme avant :
 * en flex-column, le main vit ENTRE TopBar et BottomNav. Le contenu
 * s'arrête aux limites des barres → le `backdrop-blur` n'a rien à
 * flouter, l'effet glass est invisible. En layered, le main couvre
 * tout et le contenu défile sous les barres → le blur fonctionne.
 *
 * Wrapping flexible :
 *   - Pas de TopBar : `hideTopBar`.
 *   - Pas de BottomNav (ex. /onboarding wizard) : `hideBottomNav`.
 *   - Slot custom au pied de page (rare) : `bottomSlot` remplace BottomNav.
 *   - TopBar props (initial, dotsActive, back…) : `topBarProps`.
 *
 * Responsive fallback (tablet / desktop ≥ 768px) : on encadre la shell
 * dans un container portrait de 420px max, centré horizontalement, avec
 * un fond neutre assombri sur les côtés. Les éléments internes (TopBar,
 * BottomNav, main) sont en `absolute inset-0` relatifs à ce container,
 * donc tout reste cohérent. Sur < 768px (mobile), le container occupe
 * 100% de la largeur et la mise en page est strictement identique à
 * avant. 3 (chat coordinateur).
 *
 * À l'usage :
 *
 *   return (
 *     <AppShell topBarProps={{ initial: 'M' }}>
 *       <div className="px-4 pt-4 pb-6">…contenu scrollable…</div>
 *     </AppShell>
 *   );
 */

import type { ReactNode } from 'react';
import {
  TopBar,
  type TopBarProps,
  TOPBAR_TOUCH_HEIGHT,
  TOPBAR_INSET_FALLBACK,
} from './TopBar';
import { BottomNav } from './BottomNav';
import { cn } from '@/lib/utils';

const BOTTOMNAV_TOUCH_HEIGHT = 56;

export interface AppShellProps {
  children: ReactNode;
  /** Masque la BottomNav (ex. /onboarding, /checkin avec submit propre). */
  hideBottomNav?: boolean;
  /** Masque la TopBar (cas exceptionnels — par défaut la TopBar est visible). */
  hideTopBar?: boolean;
  /** Slot remplaçant BottomNav (ex. SubmitButton sur /checkin). */
  bottomSlot?: ReactNode;
  /** Props forwardées à TopBar (initial, dotsActive, back, …). */
  topBarProps?: TopBarProps;
  /** Classes CSS additionnelles sur le wrapper externe (rare). */
  className?: string;
  /** Classes CSS additionnelles sur le `<main>` scrollable. */
  mainClassName?: string;
  /**
   * Désactive le padding-top/bottom calculé sur le `<main>`. À utiliser
   * quand on délègue le scroll à un container interne (ex. TabsLayout
   * pager horizontal) qui veut occuper tout le viewport et gérer
   * lui-même les insets — sans ça, le contenu ne peut pas défiler
   * derrière TopBar/BottomNav et l'effet glass disparaît.
   */
  disableMainPadding?: boolean;
}

export function AppShell({
  children,
  hideBottomNav = false,
  hideTopBar = false,
  bottomSlot,
  topBarProps,
  className,
  mainClassName,
  disableMainPadding = false,
}: AppShellProps) {
  const showBottomBar = bottomSlot != null || !hideBottomNav;

  // Padding-top du main = hauteur effective de la TopBar = touch-height +
  // max(fallback, safe-area-inset-top). Aligné sur le calcul interne de
  // TopBar pour que le contenu commence pile sous la barre, peu importe
  // la safe-area du device (iPhone Pro avec encoche, iPhone SE sans, etc).
  // Padding-bottom du main = hauteur de la BottomNav + safe-area iOS,
  // pour que le contenu en bas ne soit pas masqué quand on a scrollé
  // jusqu'au bout.
  // Si `disableMainPadding`, on remet à 0 dans les deux directions —
  // c'est au consommateur (ex. TabsLayout) d'ajouter ces insets au
  // niveau de son contenu interne pour que le scroll passe DERRIÈRE
  // les barres et préserve l'effet glass.
  const mainPaddingTop =
    disableMainPadding || hideTopBar
      ? '0px'
      : `calc(${TOPBAR_TOUCH_HEIGHT}px + max(${TOPBAR_INSET_FALLBACK}px, env(safe-area-inset-top)))`;
  const mainPaddingBottom =
    disableMainPadding || !showBottomBar
      ? '0px'
      : `calc(${BOTTOMNAV_TOUCH_HEIGHT}px + env(safe-area-inset-bottom))`;

  return (
    // Outer wrapper — gère le centrage + fond neutre côté tablette / desktop.
    // Sur mobile (< 768px) : occupe 100% de la largeur, aucune différence.
    // Sur ≥ 768px : encadre la shell dans un device frame de 420px max,
    // centrée, avec un fond `bg-background` autour. Pas de bordure /
    // ring pour rester sobre — c'est une fallback, pas le visuel cible.
    <div className="bg-background relative mx-auto flex h-full w-full justify-center overflow-hidden md:max-w-[420px] md:shadow-2xl md:ring-1 md:ring-white/5">
      <div
        className={cn(
          'relative h-full w-full overflow-hidden',
          // `bg-background` reste comme couche de fond ultime (pour les
          // safe-areas et avant que le gradient ne charge). Le gradient
          // signature s'applique en surimpression via la div suivante.
          'bg-background',
          className,
        )}
      >
        {/* Gradient signature : présent sur TOUTES les pages, ne scroll
            pas avec le contenu. */}
        <div
          aria-hidden="true"
          className="bg-signature pointer-events-none absolute inset-0"
        />

        {/* Main scrollable — couvre tout le viewport, le contenu défile
            DERRIÈRE TopBar / BottomNav (effet glass). */}
        <main
          className={cn(
            'scrollbar-hide absolute inset-0 overflow-y-auto overflow-x-hidden overscroll-contain',
            mainClassName,
          )}
          style={{
            paddingTop: mainPaddingTop,
            paddingBottom: mainPaddingBottom,
            WebkitOverflowScrolling: 'touch',
          }}
        >
          {children}
        </main>

        {/* TopBar absolute (z=30) — translucent + backdrop-blur. */}
        {!hideTopBar ? (
          <div className="absolute top-0 right-0 left-0 z-30">
            <TopBar {...(topBarProps ?? {})} />
          </div>
        ) : null}

        {/* BottomNav (ou bottomSlot custom) absolute (z=30). */}
        {showBottomBar ? (
          <div className="absolute right-0 bottom-0 left-0 z-30">
            {bottomSlot ?? <BottomNav />}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default AppShell;
