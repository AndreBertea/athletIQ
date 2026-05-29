/**
 * ErrorBoundary — capture les erreurs de render React pour éviter l'écran
 * blanc total de l'app.
 *
 * Contexte : une anomalie de données (ex. un tableau attendu qui arrive
 * `null` depuis l'état serveur) peut faire planter un `useMemo`/`.filter`
 * pendant le render. Sans frontière, React démonte tout l'arbre et l'écran
 * devient blanc — c'est ce qui se produisait en production sur /home.
 *
 * Cette frontière isole le crash : elle affiche un fallback exploitable
 * (avec recharger / réessayer) au lieu de tuer l'application entière.
 *
 * NB : un ErrorBoundary ne capture QUE les erreurs de render/lifecycle des
 * descendants. Les erreurs asynchrones (fetch, handlers) restent gérées
 * ailleurs (React Query, try/catch).
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Fallback custom optionnel ; sinon UI par défaut ci-dessous. */
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    // Trace lisible en prod (la stack minifiée seule est inexploitable).
    console.error('[ErrorBoundary] render crash:', error, info.componentStack);
  }

  private handleReload = (): void => {
    window.location.reload();
  };

  override render(): ReactNode {
    if (!this.state.error) return this.props.children;
    if (this.props.fallback !== undefined) return this.props.fallback;

    return (
      <main className="bg-signature flex h-dvh w-full flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-eyebrow text-muted-foreground">Une erreur est survenue</p>
        <h1 className="font-display text-xl font-bold text-foreground">
          Impossible d'afficher cette page
        </h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          Un imprévu a interrompu l'affichage. Tes données sont intactes —
          recharge la page pour reprendre.
        </p>
        <button
          type="button"
          onClick={this.handleReload}
          className="mt-2 rounded-full bg-brand-primary px-5 py-2 text-sm font-semibold text-white transition active:opacity-90"
        >
          Recharger
        </button>
      </main>
    );
  }
}
