/**
 * ContextTagsSheet — Q6 du check-in.
 *
 * Bottom sheet qui expose les 9 tags fermés (CONTEXT_TAGS) en grille 3×3.
 * Multi-select capé à 5 tags, retour `ContextTagCode[]` au parent.
 *
 * Visuel : portage 1:1 de l'overlay 05-C (screens.jsx ligne 890) — sheet
 * glass, drag-handle, pills cyan-soft pour les tags actifs.
 *
 * Pas de Radix — V1 reste sobre. Implémentation maison : Escape pour
 * fermer, click backdrop pour fermer, focus auto sur le bouton primaire
 * à l'ouverture, restitution focus à la fermeture.
 */

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  CONTEXT_TAGS,
  type ContextTag,
  type ContextTagCode,
} from '@/lib/checkin/contextTags';
import { cn } from '@/lib/utils';

const MAX_SELECTION = 5;

export interface ContextTagsSheetProps {
  /** Tags actuellement enregistrés sur l'entrée. */
  value: readonly ContextTagCode[];
  /** Callback déclenché quand on confirme la sélection. */
  onConfirm: (tags: ContextTagCode[]) => void;
  /**
   * Render prop pour le déclencheur (bouton ouvrant la sheet). Reçoit la
   * fonction d'ouverture pour permettre au parent d'utiliser son propre
   * style d'amorce (dashed cyan ou ghost). Le parent contrôle le rendu
   * du nombre de tags sélectionnés.
   */
  trigger: (open: () => void) => React.ReactNode;
}

interface InternalSheetProps {
  initialValue: readonly ContextTagCode[];
  onClose: () => void;
  onConfirm: (tags: ContextTagCode[]) => void;
}

export function ContextTagsSheet({
  value,
  onConfirm,
  trigger,
}: ContextTagsSheetProps) {
  const [open, setOpen] = useState(false);
  const handleOpen = useCallback(() => setOpen(true), []);
  const handleClose = useCallback(() => setOpen(false), []);
  const handleConfirm = useCallback(
    (tags: ContextTagCode[]) => {
      onConfirm(tags);
      setOpen(false);
    },
    [onConfirm],
  );

  return (
    <>
      {trigger(handleOpen)}
      {open ? (
        <Sheet
          initialValue={value}
          onClose={handleClose}
          onConfirm={handleConfirm}
        />
      ) : null}
    </>
  );
}

function Sheet({ initialValue, onClose, onConfirm }: InternalSheetProps) {
  const { t } = useTranslation();
  const titleId = useId();
  const descId = useId();
  const [selected, setSelected] = useState<readonly ContextTagCode[]>(
    initialValue,
  );
  const previousActive = useRef<HTMLElement | null>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  // Focus management : sauvegarde l'élément actif, restitue à la fermeture.
  useEffect(() => {
    previousActive.current =
      typeof document === 'undefined'
        ? null
        : (document.activeElement as HTMLElement | null);
    confirmRef.current?.focus();
    return () => {
      previousActive.current?.focus?.();
    };
  }, []);

  // Escape pour fermer.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // Bloquer le scroll body pendant l'overlay.
  useEffect(() => {
    const original = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = original;
    };
  }, []);

  const toggleTag = useCallback((code: ContextTagCode) => {
    setSelected((prev) => {
      if (prev.includes(code)) return prev.filter((c) => c !== code);
      if (prev.length >= MAX_SELECTION) return prev;
      return [...prev, code];
    });
  }, []);

  const handleClear = useCallback(() => setSelected([]), []);

  const remaining = MAX_SELECTION - selected.length;
  const helperText = useMemo(() => {
    if (selected.length === 0) {
      return t('checkin.context.helperEmpty', { max: MAX_SELECTION });
    }
    if (remaining <= 0) {
      return t('checkin.context.helperFull', { max: MAX_SELECTION });
    }
    return t('checkin.context.helperCount', {
      count: selected.length,
      max: MAX_SELECTION,
    });
  }, [remaining, selected.length, t]);

  // Portail vers `document.body` : sans ça, le `fixed inset-0 z-50` est
  // piégé dans le stacking context du `<main>` de l'AppShell, donc
  // visuellement *en dessous* du BottomNav (z-30 sur un layer parent).
  // Le portail sort la sheet de l'arbre React local et la rend au top
  // niveau, garantissant que `z-50` couvre vraiment toute l'interface
  // y compris la BottomNav et la TopBar.
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descId}
      className="fixed inset-0 z-[60] flex flex-col"
    >
      <button
        type="button"
        aria-label={t('checkin.context.closeAriaLabel')}
        onClick={onClose}
        className="absolute inset-0 bg-background/60 backdrop-blur-sm"
      />
      <div
        role="document"
        className={cn(
          'glass relative mt-auto flex max-h-[80vh] flex-col gap-4 px-6 pt-2 pb-6',
          'border-border-subtle border-t shadow-lg',
          'rounded-t-[20px]',
        )}
        style={{
          background: 'rgba(15, 23, 42, 0.85)',
          backdropFilter: 'blur(16px) saturate(160%)',
          WebkitBackdropFilter: 'blur(16px) saturate(160%)',
        }}
      >
        <div
          aria-hidden="true"
          className="bg-foreground/20 mx-auto mt-2 mb-2 h-1 w-10 rounded-full"
        />
        <div className="flex flex-col gap-1">
          <h2
            id={titleId}
            className="text-foreground font-text text-2xl font-bold tracking-tight"
          >
            {t('checkin.context.title')}
          </h2>
          <p
            id={descId}
            className="text-muted-foreground font-text text-sm leading-snug"
          >
            {helperText}
          </p>
        </div>

        <div
          role="group"
          aria-label={t('checkin.context.groupAriaLabel')}
          className="grid grid-cols-3 gap-3"
        >
          {CONTEXT_TAGS.map((tag) => (
            <TagPill
              key={tag.code}
              tag={tag}
              selected={selected.includes(tag.code)}
              disabled={
                !selected.includes(tag.code) && selected.length >= MAX_SELECTION
              }
              onToggle={() => toggleTag(tag.code)}
            />
          ))}
        </div>

        <div className="mt-2 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={handleClear}
            disabled={selected.length === 0}
            className={cn(
              'text-muted-foreground hover:text-foreground font-text text-xs font-medium tracking-wide uppercase transition',
              'disabled:cursor-not-allowed disabled:opacity-40',
            )}
          >
            {t('checkin.context.clear')}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={() => onConfirm([...selected])}
            className={cn(
              'bg-brand-primary text-foreground shadow-glow-primary h-12 flex-1 rounded-full font-text text-sm font-semibold tracking-wide transition',
              'hover:brightness-110',
            )}
          >
            {t('checkin.context.confirm')}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

interface TagPillProps {
  tag: ContextTag;
  selected: boolean;
  disabled: boolean;
  onToggle: () => void;
}

function TagPill({ tag, selected, disabled, onToggle }: TagPillProps) {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={selected}
      aria-disabled={disabled}
      disabled={disabled && !selected}
      onClick={onToggle}
      className={cn(
        'flex min-h-[44px] items-center justify-center gap-2 rounded-full border px-3.5 py-2.5 transition',
        'font-text text-[13px] font-medium leading-tight text-center',
        selected
          ? 'border-brand-cyan bg-brand-cyan/15 text-brand-cyan shadow-glow-cyan'
          : 'border-border-subtle text-foreground bg-foreground/5 hover:border-border',
        disabled && !selected
          ? 'cursor-not-allowed opacity-40 hover:border-border-subtle'
          : '',
      )}
    >
      <span aria-hidden="true" className="text-base leading-none">
        {tag.emoji}
      </span>
      <span>{t(`checkin.context.tags.${tag.code}`)}</span>
    </button>
  );
}

export default ContextTagsSheet;
