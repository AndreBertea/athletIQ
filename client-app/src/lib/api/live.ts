// LiveTrack via Supabase (migration de l'ancien backend Render).
//
// - createSession : parse l'URL LiveTrack et insere une ligne dans live_sessions.
//   Le relais maison (worker H24) la detecte, scrape la page Garmin et insere les
//   trackpoints dans live_trackpoints.
// - followSession : abonnement Supabase Realtime (INSERT sur live_trackpoints +
//   changement de statut sur live_sessions) — remplace l'ancien WebSocket.
//
// L'interface publique (types + methodes du LiveService) est conservee a
// l'identique : les pages live.tsx / live-session.tsx / live-shared.tsx et les
// composants n'ont pas besoin de changer.
import { supabase } from '@/lib/supabase'

export type LiveSessionSource = 'livetrack' | 'connect_iq'
export type LiveSessionStatus = 'active' | 'finished' | 'stopped'

export interface LiveSession {
  id: string
  user_id: string
  source: LiveSessionSource
  label: string | null
  status: LiveSessionStatus
  started_at: string | null
  ended_at: string | null
  last_point_at: string | null
  created_at: string
  updated_at: string
}

export interface LiveTrackpoint {
  ts: number
  lat: number | null
  lng: number | null
  hr: number | null
  speed: number | null
  cadence: number | null
  power: number | null
  distance: number | null
  altitude: number | null
}

export interface LiveSessionDetail extends LiveSession {
  points: LiveTrackpoint[]
}

export interface SharedSessionEntry {
  session: LiveSession
  athlete_id: string
  athlete_full_name: string
  athlete_email: string
}

export type LiveWsMessage =
  | { type: 'snapshot'; session: LiveSession; points: LiveTrackpoint[] }
  | { type: 'points'; points: LiveTrackpoint[] }
  | { type: 'ended'; status: LiveSessionStatus }

const SESSION_COLS =
  'id,user_id,source,label,status,started_at,ended_at,last_point_at,created_at,updated_at'

// https://livetrack.garmin.com/session/{sessionId}/token/{token}
const LIVETRACK_URL_RE = /livetrack\.garmin\.com\/session\/([^/?#]+)\/token\/([^/?#]+)/i

function mapPoint(row: Record<string, unknown>): LiveTrackpoint {
  return {
    ts: Number(row.ts),
    lat: row.lat == null ? null : Number(row.lat),
    lng: row.lng == null ? null : Number(row.lng),
    hr: row.hr == null ? null : Number(row.hr),
    speed: row.speed == null ? null : Number(row.speed),
    cadence: row.cadence == null ? null : Number(row.cadence),
    power: row.power == null ? null : Number(row.power),
    distance: row.distance == null ? null : Number(row.distance),
    altitude: row.altitude == null ? null : Number(row.altitude),
  }
}

class LiveService {
  private async currentUserId(): Promise<string> {
    const { data, error } = await supabase.auth.getUser()
    if (error || !data.user) throw new Error('Session requise.')
    return data.user.id
  }

  async createSession(url: string, label?: string): Promise<LiveSession> {
    const match = LIVETRACK_URL_RE.exec(url)
    if (!match) {
      throw new Error(
        'URL LiveTrack invalide. Format attendu : ' +
          'https://livetrack.garmin.com/session/{sessionId}/token/{token}',
      )
    }
    const [, garminSessionId, garminToken] = match
    const userId = await this.currentUserId()

    // Reutilise une session active existante pour ce meme partage Garmin.
    const { data: existing } = await supabase
      .from('live_sessions')
      .select(SESSION_COLS)
      .eq('user_id', userId)
      .eq('garmin_session_id', garminSessionId)
      .eq('status', 'active')
      .maybeSingle()
    if (existing) return existing as LiveSession

    const { data, error } = await supabase
      .from('live_sessions')
      .insert({
        user_id: userId,
        source: 'livetrack',
        label: label ?? null,
        status: 'active',
        garmin_session_id: garminSessionId,
        garmin_token: garminToken,
      })
      .select(SESSION_COLS)
      .single()
    if (error) throw new Error(error.message)
    return data as LiveSession
  }

  async listSessions(): Promise<LiveSession[]> {
    const { data, error } = await supabase
      .from('live_sessions')
      .select(SESSION_COLS)
      .order('created_at', { ascending: false })
    if (error) throw new Error(error.message)
    return (data ?? []) as LiveSession[]
  }

  async getSession(id: string): Promise<LiveSessionDetail> {
    const { data: session, error } = await supabase
      .from('live_sessions')
      .select(SESSION_COLS)
      .eq('id', id)
      .single()
    if (error) throw new Error(error.message)
    const { data: points } = await supabase
      .from('live_trackpoints')
      .select('ts,lat,lng,hr,speed,cadence,power,distance,altitude')
      .eq('session_id', id)
      .order('ts', { ascending: true })
    return { ...(session as LiveSession), points: (points ?? []).map(mapPoint) }
  }

  async deleteSession(id: string): Promise<void> {
    const { error } = await supabase.from('live_sessions').delete().eq('id', id)
    if (error) throw new Error(error.message)
  }

  // Fonctionnalite coach (sessions partagees) : non migree sur Supabase pour
  // l'instant. Retourne une liste vide plutot que d'echouer.
  async listSharedActiveSessions(): Promise<SharedSessionEntry[]> {
    return []
  }

  /**
   * Suit une session en temps reel via Supabase Realtime. Emet d'abord un
   * 'snapshot' (etat + points existants), puis 'points' a chaque nouvel INSERT,
   * et 'ended' quand le statut passe a finished/stopped. Retourne { close() }.
   */
  followSession(
    id: string,
    handlers: {
      onMessage: (msg: LiveWsMessage) => void
      onStatusChange?: (status: 'connecting' | 'open' | 'closed' | 'reconnecting') => void
    },
  ): { close: () => void } {
    let closed = false
    handlers.onStatusChange?.('connecting')

    const emitSnapshot = () => {
      this.getSession(id)
        .then((detail) => {
          if (closed) return
          const { points, ...session } = detail
          handlers.onMessage({ type: 'snapshot', session, points })
        })
        .catch(() => {
          if (!closed) handlers.onStatusChange?.('reconnecting')
        })
    }

    // Charge l'etat initial sans attendre l'abonnement Realtime. Sinon une
    // session existante peut afficher une carte vide quand Realtime tarde.
    emitSnapshot()

    const channel = supabase
      .channel(`live:${id}`)
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'live_trackpoints', filter: `session_id=eq.${id}` },
        (payload) => {
          if (closed) return
          handlers.onMessage({ type: 'points', points: [mapPoint(payload.new as Record<string, unknown>)] })
        },
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'live_sessions', filter: `id=eq.${id}` },
        (payload) => {
          if (closed) return
          const status = (payload.new as Record<string, unknown>).status as LiveSessionStatus
          if (status && status !== 'active') handlers.onMessage({ type: 'ended', status })
        },
      )
      .subscribe((status) => {
        if (closed) return
        if (status === 'SUBSCRIBED') {
          handlers.onStatusChange?.('open')
          // Re-snapshot une fois abonne : les points arrives entre-temps sont
          // inclus et le caller remplace son etat sans doublons.
          emitSnapshot()
        } else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
          handlers.onStatusChange?.('reconnecting')
        } else if (status === 'CLOSED') {
          handlers.onStatusChange?.('closed')
        }
      })

    return {
      close: () => {
        closed = true
        supabase.removeChannel(channel)
      },
    }
  }
}

export const liveService = new LiveService()
