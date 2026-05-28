import React, { createContext, useContext, useEffect, useState } from 'react'
import type { User as SupabaseUser } from '@supabase/supabase-js'
import { supabase } from '../services/supabaseClient'

interface User {
  id: string
  email: string
  full_name: string
  created_at: string
}

interface AuthContextType {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => void
  refreshToken: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

function mapUser(user: SupabaseUser): User {
  const fullName = typeof user.user_metadata?.full_name === 'string'
    ? user.user_metadata.full_name
    : ''
  return {
    id: user.id,
    email: user.email ?? '',
    full_name: fullName,
    created_at: user.created_at,
  }
}

async function upsertProfile(user: SupabaseUser, fullName?: string): Promise<void> {
  await supabase.from('profiles').upsert({
    id: user.id,
    email: user.email,
    full_name: fullName ?? user.user_metadata?.full_name ?? '',
    display_name: fullName ?? user.user_metadata?.full_name ?? user.email?.split('@')[0] ?? 'Athlète',
  })
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return
      setUser(data.session?.user ? mapUser(data.session.user) : null)
      setLoading(false)
    })

    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ? mapUser(session.user) : null)
      setLoading(false)
    })

    return () => {
      mounted = false
      listener.subscription.unsubscribe()
    }
  }, [])

  const login = async (email: string, password: string) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    })
    if (error) throw error
    if (data.user) await upsertProfile(data.user)
  }

  const signup = async (email: string, password: string, fullName: string) => {
    const { data, error } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: { data: { full_name: fullName } },
    })
    if (error) throw error
    if (data.user) await upsertProfile(data.user, fullName)
  }

  const logout = () => {
    void supabase.auth.signOut()
    setUser(null)
  }

  const refreshToken = async () => {
    const { error } = await supabase.auth.refreshSession()
    if (error) throw error
  }

  const value = {
    user,
    loading,
    login,
    signup,
    logout,
    refreshToken,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
