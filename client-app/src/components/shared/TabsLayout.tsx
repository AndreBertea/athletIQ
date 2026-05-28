/**
 * TabsLayout — pager horizontal entre /home, /history et /profile.
 *
 * Source visuelle : aligné sur AppShell (TopBar + BottomNav fixes,
 * `bg-signature` derrière). Inspiration : navigation iOS native — les
 * 3 onglets sont montés en permanence dans un container scroll-snap
 * horizontal, on swipe entre eux, l'URL suit, le tap BottomNav glisse
 * smooth jusqu'au tab cible.
 *
 * Architecture :
 *   - 1 unique <AppShell> (TopBar + BottomNav + bg-signature) monté
 *     pour les 3 routes auth principales. AppShell est wrappé par une
 *     route parent commune dans App.tsx → React Router ne démonte pas
 *     TabsLayout quand on change de tab (les sous-routes /home /history
 *     /profile sont des `element={null}`).
 *   - Le `<main>` d'AppShell est forcé en `overflow-hidden` via
 *     `mainClassName`. Le scroll horizontal vit sur une div interne
 *     `h-full w-full overflow-x-auto overflow-y-hidden snap-x
 *     snap-mandatory flex`. Cette div EST le scroll container — ref +
 *     onScroll y sont attachés.
 *   - 3 panels enfants (`shrink-0 w-full h-full snap-start
 *     overflow-y-auto`), chacun avec son propre scroll vertical. Le
 *     contenu interne (heatmap 30 cells, liste settings) défile dedans
 *     sans interférer avec le swipe horizontal global.
 *   - Les hooks de chaque content (useTodayEntry, useHistory, useProfile)
 *     ne sont plus remontés à chaque switch d'onglet — ils restent vivants
 *     en arrière-plan. Coût : useHistory(30) en plus au boot, mais ça
 *     reste 1 query (cache TanStack partagé).
 *
 * Sync URL ↔ scroll (les deux sens) :
 *   1. URL change (ex. tap BottomNav) → useEffect détecte le nouveau
 *      tab actif, appelle `scrollTo({ left: i*W, behavior: 'smooth' })`
 *      sur le container. Le `behavior: smooth` anime la transition
 *      latérale, en passant visuellement par les onglets intermédiaires.
 *   2. User swipe → onScroll fire en continu ; on calcule l'index visible
 *      par arrondi, et si différent du pathname courant, on `navigate`
 *      vers le bon tab (replace pour ne pas polluer l'historique).
 *
 * Garde anti-feedback-loop : un flag `isProgrammaticScroll` empêche le
 * onScroll de déclencher un navigate quand le scroll est issu de l'effet
 * URL→scroll (sinon : URL change → effet → scroll → onScroll → navigate
 * → URL change → boucle).
 *
 * iOS Safari quirks pris en compte :
 *   - `WebkitOverflowScrolling: 'touch'` pour momentum scrolling fluide.
 *   - `scroll-snap-type: x mandatory` est respecté à la fois pour le
 *     swipe natif et le scrollTo programmatique sur iOS 17+.
 *   - `overscroll-behavior-x: contain` empêche le pull-to-refresh sur
 *     les bords latéraux du pager.
 */

import { useEffect, useLayoutEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { AppShell } from './AppShell';
import { TOPBAR_TOUCH_HEIGHT, TOPBAR_INSET_FALLBACK } from './TopBar';
import { useAuth } from '@/contexts/AuthContext';
import { HomeContent } from '@/routes/home';
import { HistoryContent } from '@/routes/history';
import { ProfileContent } from '@/routes/profile';

const BOTTOMNAV_TOUCH_HEIGHT = 56;

// Insets calculés en CSS env() pour rester dynamiques device-side. Repris
// 1:1 d'AppShell — quand `disableMainPadding` est passé, c'est ici qu'on
// porte ces valeurs sur les panels pour que leur scroll vertical passe
// DERRIÈRE TopBar/BottomNav (effet glass restauré).
const PANEL_PADDING_TOP = `calc(${TOPBAR_TOUCH_HEIGHT}px + max(${TOPBAR_INSET_FALLBACK}px, env(safe-area-inset-top)))`;
const PANEL_PADDING_BOTTOM = `calc(${BOTTOMNAV_TOUCH_HEIGHT}px + env(safe-area-inset-bottom))`;

const TABS = [
  { path: '/home' },
  { path: '/history' },
  { path: '/profile' },
] as const;

type TabPath = (typeof TABS)[number]['path'];

function findTabIndex(pathname: string): number {
  // startsWith pour tolérer un éventuel /home/foo (pas de sous-routes
  // aujourd'hui mais on reste robuste).
  return TABS.findIndex((t) => pathname.startsWith(t.path));
}

export function TabsLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const containerRef = useRef<HTMLDivElement>(null);

  /**
   * Flag levé pendant l'animation d'un scrollTo programmatique. Tant
   * qu'il est haut, onScroll ignore les events pour ne pas déclencher
   * un navigate parasite.
   */
  const isProgrammaticScroll = useRef(false);

  const activeIndex = findTabIndex(location.pathname);

  // Sync initial : positionne le scroll sur l'onglet actif au montage,
  // SANS animation (pour éviter un slide-in visible au load). useLayoutEffect
  // garantit que la position est posée avant le premier paint.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el || activeIndex < 0) return;
    const target = activeIndex * el.clientWidth;
    isProgrammaticScroll.current = true;
    el.scrollTo({ left: target, behavior: 'auto' });
    requestAnimationFrame(() => {
      isProgrammaticScroll.current = false;
    });
    // ⚠️ Ne dépend QUE de activeIndex au montage initial. Les swipes
    // ultérieurs sont gérés par l'autre useEffect ci-dessous (smooth).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync URL→scroll : à chaque changement d'index actif, on glisse
  // smooth vers le tab cible. C'est l'animation du tap BottomNav.
  //
  // Tolérance large (un demi viewport) : si l'URL a changé À CAUSE D'UN
  // SWIPE en cours, on ne refire PAS un scrollTo (le snap-mandatory du
  // navigateur va déjà faire le boulot après release du touch). On
  // ne déclenche le scrollTo que si la distance dépasse 0.5 panel —
  // typique d'un tap BottomNav (jump de 1+ panel) ou d'une nav
  // programmatique cross-tab.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || activeIndex < 0) return;
    const w = el.clientWidth;
    if (w === 0) return;
    const target = activeIndex * w;
    const distance = Math.abs(el.scrollLeft - target);
    // Si on est à moins d'un demi-panel du target, on laisse le snap
    // natif se charger de la suite (cas swipe). Sinon on glisse smooth
    // (cas tap BottomNav qui peut sauter 1 ou 2 panels d'un coup).
    if (distance < w * 0.5) return;
    isProgrammaticScroll.current = true;
    el.scrollTo({ left: target, behavior: 'smooth' });
    // Le scrollTo smooth peut prendre ~300-500ms ; on libère le flag
    // après ce délai pour être sûr d'avoir laissé l'animation finir.
    const t = window.setTimeout(() => {
      isProgrammaticScroll.current = false;
    }, 450);
    return () => window.clearTimeout(t);
  }, [activeIndex]);

  // Resize : si le viewport change (rotation tablet, redim desktop fenêtre),
  // recalibrer la position pour rester aligné sur l'index actif. Sans ça,
  // après resize, le scroll-snap pourrait se figer entre 2 tabs.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onResize = () => {
      if (activeIndex < 0) return;
      isProgrammaticScroll.current = true;
      el.scrollTo({ left: activeIndex * el.clientWidth, behavior: 'auto' });
      requestAnimationFrame(() => {
        isProgrammaticScroll.current = false;
      });
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [activeIndex]);

  const onScroll = () => {
    if (isProgrammaticScroll.current) return;
    const el = containerRef.current;
    if (!el) return;
    const w = el.clientWidth;
    if (w === 0) return;
    const i = Math.round(el.scrollLeft / w);
    const target = TABS[i];
    if (!target) return;
    if (target.path === location.pathname) return;
    // replace: true → on n'empile pas l'historique en swipant.
    navigate(target.path, { replace: true });
  };

  // TopBar partage la même initiale pour les 3 onglets — c'est l'utilisateur
  // courant. Pas besoin de recalculer par tab.
  const initial = user?.displayName.charAt(0).toUpperCase() ?? 'M';

  return (
    <AppShell
      topBarProps={{ initial }}
      // On force AppShell.main en `overflow-hidden` — le scroll vit
      // sur la div interne ci-dessous (notre vrai scroll container).
      // `!important` (`!`) bat les classes par défaut de main.
      // `disableMainPadding` : sinon le main aurait un padding-top/bottom
      // qui empêcherait les panels de défiler DERRIÈRE TopBar/BottomNav
      // (effet glass cassé). On gère le padding au niveau Panel à la place.
      mainClassName="!overflow-hidden"
      disableMainPadding
    >
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="scrollbar-hide flex h-full w-full snap-x snap-mandatory overflow-x-auto overflow-y-hidden"
        style={{
          WebkitOverflowScrolling: 'touch',
          overscrollBehaviorX: 'contain',
        }}
      >
        <Panel path="/home">
          <HomeContent />
        </Panel>
        <Panel path="/history">
          <HistoryContent />
        </Panel>
        <Panel path="/profile">
          <ProfileContent />
        </Panel>
      </div>
    </AppShell>
  );
}

/**
 * Panel — un onglet dans le pager. Largeur = 100% du scroll container,
 * hauteur = 100% (étiré par le flex parent), scroll vertical interne.
 *
 * `snap-start` aligne le bord gauche du panel sur le bord gauche du
 * scroll container quand le snap se déclenche.
 *
 * ⚠️ overflow-y-auto sur le panel ET overflow-y-hidden sur le container
 * = scroll vertical CAPTURÉ par le panel (la heatmap, la liste de settings,
 * etc. peuvent défiler verticalement sans interférer avec le swipe
 * horizontal).
 */
function Panel({ path, children }: { path: TabPath; children: React.ReactNode }) {
  // Le panel s'étend désormais du top:0 au bottom:0 du viewport. Son
  // `padding-top` = hauteur effective de la TopBar et `padding-bottom`
  // = hauteur effective de la BottomNav, pour que le contenu commence
  // visuellement sous TopBar et se termine au-dessus de BottomNav,
  // tout en pouvant DÉFILER DERRIÈRE elles → effet glass préservé.
  return (
    <section
      data-tab-path={path}
      className="scrollbar-hide h-full w-full shrink-0 snap-start overflow-y-auto overflow-x-hidden overscroll-contain"
      style={{
        WebkitOverflowScrolling: 'touch',
        paddingTop: PANEL_PADDING_TOP,
        paddingBottom: PANEL_PADDING_BOTTOM,
      }}
    >
      {children}
    </section>
  );
}

export default TabsLayout;
