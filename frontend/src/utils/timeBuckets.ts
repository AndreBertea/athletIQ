import { format, parseISO } from 'date-fns'
import { fr } from 'date-fns/locale'

export type TimeGranularity = 'day' | 'week' | 'month'

export const GRANULARITY_LABELS: Record<TimeGranularity, string> = {
  day: '1j',
  week: '1s',
  month: '1m',
}

export const GRANULARITY_DESCRIPTIONS: Record<TimeGranularity, string> = {
  day: 'par jour',
  week: 'par semaine',
  month: 'par mois',
}

function toISODate(date: Date): string {
  return date.toISOString().split('T')[0]
}

function getBucketStart(date: Date, granularity: TimeGranularity): Date {
  const d = new Date(date)
  d.setHours(0, 0, 0, 0)
  if (granularity === 'week') {
    const day = d.getDay() // 0 = dimanche
    const diff = (day + 6) % 7 // lundi = 0
    d.setDate(d.getDate() - diff)
  } else if (granularity === 'month') {
    d.setDate(1)
  }
  return d
}

export function getBucketKey(dateIso: string, granularity: TimeGranularity): string {
  return toISODate(getBucketStart(parseISO(dateIso), granularity))
}

export function formatBucketLabel(bucketKey: string, granularity: TimeGranularity): string {
  const date = parseISO(bucketKey)
  if (granularity === 'week') {
    return `Sem. ${format(date, 'd MMM', { locale: fr })}`
  }
  if (granularity === 'month') {
    return format(date, 'MMM yy', { locale: fr })
  }
  return format(date, 'd MMM', { locale: fr })
}
