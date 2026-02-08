import { format, parseISO, isToday, isTomorrow } from 'date-fns'
import { fr } from 'date-fns/locale'

/** Formatage court : "8 fév. 2026" */
export function formatDateShort(dateStr: string): string {
  try {
    return format(parseISO(dateStr), 'd MMM yyyy', { locale: fr })
  } catch {
    return dateStr?.slice(0, 10) ?? ''
  }
}

/** Formatage long : "8 février 2026" */
export function formatDateLong(dateStr: string): string {
  try {
    return format(parseISO(dateStr), 'd MMMM yyyy', { locale: fr })
  } catch {
    return dateStr?.slice(0, 10) ?? ''
  }
}

/** Formatage relatif : "Aujourd'hui", "Demain", ou date complète */
export function formatDateRelative(dateStr: string): string {
  try {
    const date = parseISO(dateStr)
    if (isToday(date)) return "Aujourd'hui"
    if (isTomorrow(date)) return 'Demain'
    return format(date, 'EEEE d MMMM', { locale: fr })
  } catch {
    return dateStr?.slice(0, 10) ?? ''
  }
}

/** Formatage durée : "1h 23min" */
export function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}min`
  return `${m}min`
}

/** Formatage distance : "12.3 km" */
export function formatDistance(meters: number): string {
  return `${(meters / 1000).toFixed(1)} km`
}
