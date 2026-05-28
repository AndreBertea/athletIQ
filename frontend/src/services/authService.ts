import { fetchFunctionBlob, invokeFunction, supabase } from './supabaseClient'

interface StravaStatus {
  connected: boolean
  athlete_id?: number
  scope?: string
  expires_at?: string
  is_expired?: boolean
  last_sync?: string
}

interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

interface User {
  id: string
  email: string
  full_name: string
  created_at: string
}

class AuthService {
  async login(email: string, password: string): Promise<LoginResponse> {
    const { data, error } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    if (error) throw error
    return {
      access_token: data.session?.access_token ?? '',
      refresh_token: data.session?.refresh_token ?? '',
      token_type: 'bearer',
      expires_in: data.session?.expires_in ?? 0,
    }
  }

  async signup(email: string, password: string, fullName: string): Promise<LoginResponse> {
    const { data, error } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: { data: { full_name: fullName } },
    })
    if (error) throw error
    if (data.user) {
      await supabase.from('profiles').upsert({
        id: data.user.id,
        email: data.user.email,
        full_name: fullName,
        display_name: fullName,
      })
    }
    return {
      access_token: data.session?.access_token ?? '',
      refresh_token: data.session?.refresh_token ?? '',
      token_type: 'bearer',
      expires_in: data.session?.expires_in ?? 0,
    }
  }

  async getCurrentUser(): Promise<User> {
    const { data, error } = await supabase.auth.getUser()
    if (error || !data.user) throw error ?? new Error('Session Supabase requise')
    const { data: profile } = await supabase.from('profiles').select('*').eq('id', data.user.id).maybeSingle()
    return {
      id: data.user.id,
      email: data.user.email ?? profile?.email ?? '',
      full_name: profile?.full_name ?? data.user.user_metadata?.full_name ?? '',
      created_at: profile?.created_at ?? data.user.created_at,
    }
  }

  async refreshToken(): Promise<{ access_token: string }> {
    const { data, error } = await supabase.auth.refreshSession()
    if (error) throw error
    return { access_token: data.session?.access_token ?? '' }
  }

  async logout(): Promise<void> {
    await supabase.auth.signOut()
  }

  async getStravaStatus(): Promise<StravaStatus> {
    const { data, error } = await supabase.rpc('get_external_auth_status', { provider_name: 'strava' })
    if (error) return { connected: false }
    const first = Array.isArray(data) ? data[0] : data
    if (!first) return { connected: false }
    return {
      connected: true,
      athlete_id: first.provider_user_id ? Number(first.provider_user_id) : undefined,
      scope: first.scopes?.join(','),
      expires_at: first.expires_at,
      is_expired: first.is_expired,
      last_sync: first.last_sync_at,
    }
  }

  async initiateStravaLogin() {
    const result = await invokeFunction<{ url: string }>('strava-oauth-start')
    return { ...result, authorization_url: result.url }
  }

  async deleteStravaData(): Promise<{
    message: string
    deleted_activities: number
    strava_auth_deleted: boolean
  }> {
    const user = await this.getCurrentUser()
    const { count } = await supabase.from('activities').delete({ count: 'exact' }).eq('user_id', user.id).eq('source', 'strava')
    await supabase.rpc('disconnect_external_auth', { provider_name: 'strava' })
    return { message: 'Données Strava supprimées', deleted_activities: count ?? 0, strava_auth_deleted: true }
  }

  async deleteAllUserData(): Promise<{
    message: string
    deleted_activities: number
    deleted_workout_plans: number
    strava_auth_deleted: boolean
  }> {
    const user = await this.getCurrentUser()
    const { count } = await supabase.from('activities').delete({ count: 'exact' }).eq('user_id', user.id)
    await supabase.rpc('disconnect_external_auth', { provider_name: 'strava' })
    await supabase.rpc('disconnect_external_auth', { provider_name: 'garmin' })
    return { message: 'Données utilisateur supprimées', deleted_activities: count ?? 0, deleted_workout_plans: 0, strava_auth_deleted: true }
  }

  async deleteAccount(): Promise<{
    message: string
    deleted_activities: number
    deleted_workout_plans: number
    strava_auth_deleted: boolean
    account_deleted: boolean
  }> {
    await invokeFunction('delete-account', { method: 'DELETE' })
    return { message: 'Compte supprimé', deleted_activities: 0, deleted_workout_plans: 0, strava_auth_deleted: true, account_deleted: true }
  }

  async exportUserData(): Promise<Blob> {
    return await fetchFunctionBlob('data-export')
  }
}

export const authService = new AuthService()
