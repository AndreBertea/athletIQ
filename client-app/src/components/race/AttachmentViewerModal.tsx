import { useEffect, useState } from 'react';
import { Download, FileText, Loader2, X } from 'lucide-react';
import { agonApi, type GpxAttachmentRead } from '@/lib/api/agon';

interface AttachmentViewerModalProps {
  routeId: string;
  attachment: GpxAttachmentRead | null;
  onClose: () => void;
}

/**
 * Modal plein ecran qui ouvre un attachment (PDF, image, autre).
 *
 * Strategie : on telecharge le binaire via l'API authentifiee (cookies
 * httpOnly), on cree un blob URL local et on l'affiche dans une `<iframe>`
 * (PDF → viewer natif du navigateur, image → image inline).
 * Le blob URL est revoque a la fermeture pour eviter les fuites memoire.
 */
export function AttachmentViewerModal({ routeId, attachment, onClose }: AttachmentViewerModalProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!attachment) {
      setBlobUrl(null);
      setError(null);
      return;
    }
    let cancelled = false;
    let currentUrl: string | null = null;
    setError(null);
    setBlobUrl(null);
    agonApi
      .getGpxRouteAttachmentBlobUrl(routeId, attachment.id)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url);
          return;
        }
        currentUrl = url;
        setBlobUrl(url);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Lecture impossible');
        }
      });
    return () => {
      cancelled = true;
      if (currentUrl) URL.revokeObjectURL(currentUrl);
    };
  }, [routeId, attachment]);

  if (!attachment) return null;

  const isImage = attachment.kind === 'image' || attachment.mime_type.startsWith('image/');

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-md">
      <div className="border-border-subtle flex items-center justify-between border-b px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="text-brand-cyan h-5 w-5 shrink-0" />
          <div className="min-w-0">
            <p className="text-foreground truncate text-sm font-semibold">{attachment.name}</p>
            <p className="text-muted-foreground truncate text-[11px]">{attachment.filename}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {blobUrl ? (
            <a
              href={blobUrl}
              download={attachment.filename}
              className="text-muted-foreground hover:text-foreground rounded-md p-2"
              aria-label="Telecharger"
            >
              <Download className="h-4 w-4" />
            </a>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded-md p-2"
            aria-label="Fermer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>
      <div className="relative flex-1 overflow-hidden bg-black/30">
        {error ? (
          <p className="text-danger-fg p-6 text-sm">{error}</p>
        ) : !blobUrl ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : isImage ? (
          <img src={blobUrl} alt={attachment.name} className="mx-auto h-full max-h-full object-contain" />
        ) : (
          <iframe
            src={blobUrl}
            title={attachment.name}
            className="h-full w-full border-0"
          />
        )}
      </div>
    </div>
  );
}

export default AttachmentViewerModal;
