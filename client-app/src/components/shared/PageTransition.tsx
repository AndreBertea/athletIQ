/**
 * PageTransition — transitions de page facon iOS + gestes de navigation.
 *
 * - Transition : à chaque changement de route, la page entrante glisse
 *   horizontalement (push depuis la droite, pop/back depuis la gauche,
 *   swipe latéral entre onglets selon le sens). Animé via framer-motion
 *   (spring), les deux pages bougent ensemble (effet natif).
 * - Direction :
 *     • entre onglets Home/Live/Predictor → sens = comparaison d'index ;
 *     • navigation POP (back / edge-swipe) → la page entrante vient de gauche ;
 *     • sinon (push) → la page entrante vient de droite.
 * - Gestes :
 *     • swipe horizontal sur un onglet → onglet voisin (Home↔Live↔Predictor) ;
 *     • swipe depuis le bord gauche vers la droite sur une page « poussée »
 *       (ex. détail activité) → retour arrière (navigate(-1)).
 *   On ignore les swipes verticaux et ceux qui démarrent dans un conteneur
 *   à scroll horizontal (carrousels, onglets) pour ne pas voler leur geste.
 */

import {
  Suspense,
  useRef,
  useState,
  type ReactNode,
  type TouchEvent as ReactTouchEvent,
} from 'react';
import { AnimatePresence, motion, type Variants } from 'framer-motion';
import {
  useLocation,
  useNavigate,
  useNavigationType,
  useOutlet,
} from 'react-router-dom';

/** Ordre des onglets principaux pour le swipe latéral. */
const TAB_ORDER = ['/home', '/live', '/race-predictor'] as const;

/** Largeur (px) de la zone de bord gauche déclenchant le retour. */
const EDGE_WIDTH = 28;
/** Distance horizontale minimale (px) pour valider un swipe de navigation. */
const SWIPE_DISTANCE = 64;

function tabIndex(pathname: string): number {
  return TAB_ORDER.findIndex((p) => pathname === p);
}

const variants: Variants = {
  initial: (enterFromRight: boolean) => ({
    x: enterFromRight ? '100%' : '-100%',
  }),
  animate: { x: 0 },
  exit: (enterFromRight: boolean) => ({
    x: enterFromRight ? '-100%' : '100%',
  }),
};

/**
 * Fige le contenu de la page au montage (clé = pathname) : la page sortante
 * conserve son rendu pendant l'animation au lieu d'afficher la nouvelle route.
 */
function FrozenPage({
  enterFromRight,
  children,
}: {
  enterFromRight: boolean;
  children: ReactNode;
}) {
  const [frozen] = useState(children);
  return (
    <motion.div
      custom={enterFromRight}
      variants={variants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={{ type: 'spring', stiffness: 460, damping: 42, mass: 0.85 }}
      className="absolute inset-0 h-full w-full"
    >
      <Suspense fallback={<TransitionFallback />}>{frozen}</Suspense>
    </motion.div>
  );
}

function TransitionFallback() {
  return <div className="bg-signature h-full w-full" />;
}

/**
 * Clé de transition : les 3 onglets racine partagent la clé 'tabs' (le pager
 * interne gère leur swipe latéral, sans transition pleine page). Les sous-pages
 * poussées, ex. /live/:id, gardent leur pathname pour forcer le montage route.
 */
function transitionKey(pathname: string): string {
  return tabIndex(pathname) >= 0 ? 'tabs' : pathname;
}

export function PageTransition() {
  const location = useLocation();
  const navigate = useNavigate();
  const navType = useNavigationType();
  const outlet = useOutlet();

  const key = transitionKey(location.pathname);
  // Le sens n'importe qu'entre groupes (onglets ↔ page poussée) : POP =
  // retour (entrée par la gauche), sinon push (entrée par la droite).
  const enterFromRight = navType !== 'POP';

  const touch = useRef<{ x: number; y: number; edge: boolean } | null>(null);

  const onTouchStart = (event: ReactTouchEvent) => {
    const t = event.touches[0];
    if (!t) return;
    touch.current = { x: t.clientX, y: t.clientY, edge: t.clientX <= EDGE_WIDTH };
  };

  const onTouchEnd = (event: ReactTouchEvent) => {
    const start = touch.current;
    touch.current = null;
    if (!start) return;
    // Sur un onglet, le swipe latéral est géré par le pager interne. Ici on
    // ne traite que l'edge-swipe « retour » des pages poussées.
    if (tabIndex(location.pathname) >= 0) return;
    if (!start.edge) return;
    const t = event.changedTouches[0];
    if (!t) return;
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (dx < SWIPE_DISTANCE) return;
    if (Math.abs(dx) < Math.abs(dy) * 1.4) return; // pas assez horizontal
    navigate(-1);
  };

  return (
    <div
      className="relative h-dvh w-full overflow-hidden"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <AnimatePresence custom={enterFromRight} initial={false}>
        <FrozenPage key={key} enterFromRight={enterFromRight}>
          {outlet}
        </FrozenPage>
      </AnimatePresence>
    </div>
  );
}

export default PageTransition;
