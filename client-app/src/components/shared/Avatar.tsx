interface Props {
  /** Nom complet, ex: "Andre Bertea" -> "AB". Si vide, fallback "?". */
  name: string | null | undefined
  /** Couleur de fond du cercle (hex ou nom CSS). Default gris. */
  color?: string
  /** Diametre en px. Default 32. */
  size?: number
  /** Optionnel : classe Tailwind supplementaire pour le wrapper. */
  className?: string
}

/**
 * Avatar avec initiales auto-generees depuis le name.
 * - "Andre Bertea" -> "AB"
 * - "Marie" -> "M"
 * - "" / null -> "?"
 */
export default function Avatar({
  name,
  color = '#6b7280',
  size = 32,
  className = '',
}: Props) {
  const initials = computeInitials(name)
  const fontSize = Math.max(10, Math.round(size * 0.4))
  return (
    <span
      className={`inline-flex items-center justify-center rounded-full text-white font-semibold select-none flex-shrink-0 ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor: color,
        fontSize: `${fontSize}px`,
        lineHeight: 1,
      }}
      title={name || undefined}
      aria-label={name ? `Avatar ${name}` : 'Avatar'}
    >
      {initials}
    </span>
  )
}

function computeInitials(name: string | null | undefined): string {
  if (!name) return '?'
  const trimmed = name.trim()
  if (!trimmed) return '?'
  const parts = trimmed.split(/\s+/).filter(Boolean)
  if (parts.length === 1) {
    return (parts[0] ?? '?').slice(0, 2).toUpperCase()
  }
  const first = parts[0]?.[0]
  const last = parts[parts.length - 1]?.[0]
  return first && last ? (first + last).toUpperCase() : '?'
}
