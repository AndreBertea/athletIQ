import React, { createContext, useContext, useEffect, useState } from 'react'
import { authService } from '../services/authService'

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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    initializeAuth()
  }, [])

  const initializeAuth = async () => {
    try {
      // Les cookies httpOnly sont envoyés automatiquement par le navigateur
      const userData = await authService.getCurrentUser()
      setUser(userData)
    } catch {
      // Pas de session valide (pas de cookie ou cookie expiré)
    } finally {
      setLoading(false)
    }
  }

  const login = async (email: string, password: string) => {
    await authService.login(email, password)
    // Le backend a posé les cookies httpOnly, on récupère le user
    const userData = await authService.getCurrentUser()
    setUser(userData)
  }

  const signup = async (email: string, password: string, fullName: string) => {
    await authService.signup(email, password, fullName)
    // Le backend a posé les cookies httpOnly, on récupère le user
    const userData = await authService.getCurrentUser()
    setUser(userData)
  }

  const logout = () => {
    authService.logout()
    setUser(null)
  }

  const refreshToken = async () => {
    await authService.refreshToken()
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
