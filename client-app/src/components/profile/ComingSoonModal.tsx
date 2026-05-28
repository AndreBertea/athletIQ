/**
 * ComingSoonModal — modale d'attente pour les intégrations wearables V1.1.
 *
 * Aucune intégration réelle V1 — tous les boutons passent par cette
 * modale. Texte unique : « Bientôt disponible » + corps qui rappelle la
 * roadmap V1.1 + bouton OK.
 *
 * Implémentation accessible sans dépendance Radix : `<dialog>` natif
 * piloté en effet, avec backdrop click + Escape pour fermer. Un seul
 * point d'entrée par appel (`service` détermine le contenu).
 */

import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

// Whoop et Oura retirés des intégrations affichées (demande utilisateur).
// Le type côté DB (`EntrySource` dans types/database.ts) garde toutes les
// valeurs pour compatibilité avec une éventuelle V1.1, mais le profil
// utilisateur ne propose plus que les deux intégrations principales.
export type WearableService = 'apple_health' | 'garmin';

interface WearableServiceMeta {
  /** Emoji visuel — ne change pas avec la langue. Le label localisé vit
   *  dans `profile.integrations.<service>.label`. */
  emoji: string;
}

/**
 * Catalogue des intégrations affichées en V1. Le label / la description
 * humains sont résolus par le consommateur via `t()` — ce record ne sert
 * qu'à itérer sur les services et obtenir l'emoji.
 */
export const WEARABLE_SERVICES: Record<WearableService, WearableServiceMeta> = {
  apple_health: { emoji: '❤️' },
  garmin: { emoji: '⌚' },
};

interface ComingSoonModalProps {
  /** Service ciblé. Si null, la modale est fermée. */
  service: WearableService | null;
  /** Callback fermeture. */
  onClose: () => void;
}

export function ComingSoonModal({ service, onClose }: ComingSoonModalProps) {
  const { t } = useTranslation();
  const dialogRef = useRef<HTMLDialogElement | null>(null);

  // Open / close en effet pour piloter <dialog> natif.
  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    if (service && !dlg.open) {
      dlg.showModal();
    } else if (!service && dlg.open) {
      dlg.close();
    }
  }, [service]);

  // Escape natif — on intercepte 'cancel' (Escape) pour propager onClose.
  useEffect(() => {
    const dlg = dialogRef.current;
    if (!dlg) return;
    const handleCancel = (e: Event) => {
      e.preventDefault();
      onClose();
    };
    dlg.addEventListener('cancel', handleCancel);
    return () => dlg.removeEventListener('cancel', handleCancel);
  }, [onClose]);

  // Backdrop click — natif <dialog> gère ::backdrop, on détecte le click
  // hors du contenu en comparant les coords du click avec la bounding box.
  const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    const dlg = e.currentTarget;
    const rect = dlg.getBoundingClientRect();
    const inDialog =
      rect.top <= e.clientY &&
      e.clientY <= rect.top + rect.height &&
      rect.left <= e.clientX &&
      e.clientX <= rect.left + rect.width;
    if (!inDialog) onClose();
  };

  const meta = service ? WEARABLE_SERVICES[service] : null;
  const label = service ? t(`profile.integrations.${service}.label`) : '';
  const description = service
    ? t(`profile.integrations.${service}.description`)
    : '';

  return (
    <dialog
      ref={dialogRef}
      onClick={handleBackdropClick}
      className={cn(
        'rounded-lg p-0 backdrop:bg-black/60 backdrop:backdrop-blur-sm',
        'bg-transparent open:flex open:flex-col',
      )}
      aria-labelledby="coming-soon-title"
    >
      {meta ? (
        <div
          className={cn(
            'glass max-w-sm rounded-lg p-6',
            'shadow-glow-primary',
          )}
        >
          <div className="flex items-center gap-3">
            <span aria-hidden="true" className="text-2xl">
              {meta.emoji}
            </span>
            <p className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              {label}
            </p>
          </div>
          <h2
            id="coming-soon-title"
            className="font-display text-foreground mt-3 text-2xl font-bold tracking-tight"
          >
            {t('profile.comingSoon.title')}
          </h2>
          <p className="text-muted-foreground mt-3 text-sm leading-relaxed">
            {t('profile.comingSoon.body', { service: label })}
          </p>
          <p className="text-muted-foreground mt-2 text-xs">{description}</p>
          <button
            type="button"
            onClick={onClose}
            className={cn(
              'bg-brand-primary text-foreground mt-5 h-11 w-full rounded font-semibold transition',
              'hover:brightness-110',
            )}
            autoFocus
          >
            {t('common.ok')}
          </button>
        </div>
      ) : null}
    </dialog>
  );
}

export default ComingSoonModal;
