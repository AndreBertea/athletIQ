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
  return TAB_ORDER.findIndex(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

/** Remonte les ancêtres : un conteneur scrollable horizontalement capte le geste. */
function hasHorizontalScrollAncestor(target: EventTarget | null): boolean {
  let node = target as HTMLElement | null;
  while (node && node !== document.body) {
    if (node.scrollWidth > node.clientWidth + 4) {
      const overflowX = getComputedStyle(node).overflowX;
      if (overflowX === 'auto' || overflowX === 'scroll') return true;
    }
    node = node.parentElement;
  }
  return false;
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

export function PageTransition() {
  const location = useLocation();
  const navigate = useNavigate();
  const navType = useNavigationType();
  const outlet = useOutlet();
  const prevPath = useRef(location.pathname);

  const from = prevPath.current;
  const to = location.pathname;
  const fromTab = tabIndex(from);
  const toTab = tabIndex(to);

  let enterFromRight = true;
  if (fromTab >= 0 && toTab >= 0 && fromTab !== toTab) {
    enterFromRight = toTab > fromTab; // swipe/tap latéral entre onglets
  } else if (navType === 'POP') {
    enterFromRight = false; // retour (back / edge-swipe)
  } else {
    enterFromRight = true; // push (entrée dans une sous-page)
  }
  prevPath.current = to;

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
    const t = event.changedTouches[0];
    if (!t) return;
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (Math.abs(dx) < SWIPE_DISTANCE) return;
    if (Math.abs(dx) < Math.abs(dy) * 1.4) return; // pas assez horizontal
    if (hasHorizontalScrollAncestor(event.target)) return; // laisse scroller

    const current = tabIndex(location.pathname);
    if (dx > 0) {
      // Swipe vers la droite : onglet précédent, ou retour si page poussée.
      if (current > 0) navigate(TAB_ORDER[current - 1]);
      else if (current < 0 && start.edge) navigate(-1);
    } else {
      // Swipe vers la gauche : onglet suivant.
      if (current >= 0 && current < TAB_ORDER.length - 1) {
        navigate(TAB_ORDER[current + 1]);
      }
    }
  };

  return (
    <div
      className="relative h-dvh w-full overflow-hidden"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <AnimatePresence custom={enterFromRight} initial={false}>
        <FrozenPage key={location.pathname} enterFromRight={enterFromRight}>
          {outlet}
        </FrozenPage>
      </AnimatePresence>
    </div>
  );
}

export default PageTransition;
