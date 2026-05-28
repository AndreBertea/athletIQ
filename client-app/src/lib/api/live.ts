import axios from 'axios'

const VITE_API_URL = (import.meta as any).env?.VITE_API_URL
const API_BASE_URL = VITE_API_URL ? `${VITE_API_URL}/api/v1` : '/api/v1'
const WS_BASE_URL = (() => {
  const base = VITE_API_URL || window.location.origin
  return base.replace(/^http/, 'ws') + '/api/v1'
})()

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

class LiveService {
  private api = axios.create({
    baseURL: API_BASE_URL,
    headers: { 'Content-Type': 'application/json' },
    withCredentials: true,
  })

  async createSession(url: string, label?: string): Promise<LiveSession> {
    const { data } = await this.api.post<LiveSession>('/live/sessions', { url, label })
    return data
  }

  async listSessions(): Promise<LiveSession[]> {
    const { data } = await this.api.get<LiveSession[]>('/live/sessions')
    return data
  }

  async getSession(id: string): Promise<LiveSessionDetail> {
    const { data } = await this.api.get<LiveSessionDetail>(`/live/sessions/${id}`)
    return data
  }

  async deleteSession(id: string): Promise<void> {
    await this.api.delete(`/live/sessions/${id}`)
  }

  async listSharedActiveSessions(): Promise<SharedSessionEntry[]> {
    const { data } = await this.api.get<SharedSessionEntry[]>('/live/shared/active-sessions')
    return data
  }

  /**
   * Ouvre une WebSocket vers /live/follow/{id}, retourne un controleur avec
   * close(). Reconnect automatique avec backoff exponentiel (max 30s).
   * Sur reconnect, le snapshot initial est renvoye par le backend, donc le
   * caller doit simplement remplacer ses points par le nouveau snapshot.
   */
  followSession(
    id: string,
    handlers: {
      onMessage: (msg: LiveWsMessage) => void
      onStatusChange?: (status: 'connecting' | 'open' | 'closed' | 'reconnecting') => void
    },
  ): { close: () => void } {
    let ws: WebSocket | null = null
    let closed = false
    let attempt = 0
    let reconnectTimer: number | null = null

    const connect = async () => {
      if (closed) return
      handlers.onStatusChange?.(attempt === 0 ? 'connecting' : 'reconnecting')

      // 1. Recuperer un token JWT via XHR (cookie httpOnly envoye automatiquement)
      //    Les navigateurs n'envoient pas les cookies SameSite=Lax sur les WS handshakes,
      //    donc on doit passer le token en query param.
      let token: string
      try {
        const { data } = await this.api.get<{ token: string }>('/live/ws-token')
        token = data.token
      } catch (e) {
        // Si le user n'est pas auth, on ne peut pas ouvrir le WS. Retry plus tard.
        attempt += 1
        const delay = Math.min(1000 * 2 ** Math.min(attempt - 1, 5), 30000)
        reconnectTimer = window.setTimeout(connect, delay)
        return
      }
      if (closed) return

      const url = `${WS_BASE_URL}/live/follow/${id}?token=${encodeURIComponent(token)}`
      ws = new WebSocket(url)

      ws.onopen = () => {
        attempt = 0
        handlers.onStatusChange?.('open')
      }
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data) as LiveWsMessage
          handlers.onMessage(msg)
        } catch {
          // ignore non-JSON frames
        }
      }
      ws.onerror = () => {
        // onclose enchainera
      }
      ws.onclose = () => {
        if (closed) return
        handlers.onStatusChange?.('closed')
        attempt += 1
        const delay = Math.min(1000 * 2 ** Math.min(attempt - 1, 5), 30000)
        reconnectTimer = window.setTimeout(connect, delay)
      }
    }
    connect()

    return {
      close: () => {
        closed = true
        if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
        if (ws) {
          try { ws.close() } catch {/* ignore */}
        }
      },
    }
  }
}

export const liveService = new LiveService()
