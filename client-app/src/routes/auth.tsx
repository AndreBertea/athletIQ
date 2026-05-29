/**
 * Route '/' — Login + Signup style glass orange AGON.
 *
 * Pleine hauteur, gradient signature orange en arriere-plan, card glass
 * (backdrop-blur) au centre, bouton .btn-glass-primary. Mobile-first.
 *
 * Toggle login/signup dans le sous-titre. Branche sur AuthContext
 * (signIn/signUp/isLoading), backend FastAPI via proxy Vite /api.
 */

import { useState } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { toast } from 'sonner'
import { Eye, EyeOff, AlertCircle, Loader2 } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'

const loginSchema = z.object({
  email: z.string().email('Email invalide'),
  password: z.string().min(6, 'Le mot de passe doit contenir au moins 6 caracteres'),
})

const signupSchema = loginSchema.extend({
  confirmPassword: z.string(),
}).refine((data) => data.password === data.confirmPassword, {
  message: 'Les mots de passe ne correspondent pas',
  path: ['confirmPassword'],
})

type LoginFormData = z.infer<typeof loginSchema>
type SignupFormData = z.infer<typeof signupSchema>

export default function AuthRoute() {
  const [isSignup, setIsSignup] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const { user, signIn, signUp, isLoading: authLoading } = useAuth()
  const navigate = useNavigate()

  const loginForm = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema as any),
  })
  const signupForm = useForm<SignupFormData>({
    resolver: zodResolver(signupSchema as any),
  })

  if (!authLoading && user) {
    return <Navigate to="/home" replace />
  }

  const onLogin = async (data: LoginFormData) => {
    setLoading(true)
    setError(null)
    try {
      await signIn(data.email, data.password)
      toast.success('Connexion reussie')
      navigate('/home')
    } catch (err: any) {
      setError(err?.message || 'Erreur de connexion')
    } finally {
      setLoading(false)
    }
  }

  const onSignup = async (data: SignupFormData) => {
    setLoading(true)
    setError(null)
    try {
      await signUp(data.email, data.password)
      toast.success('Compte cree avec succes')
      navigate('/home')
    } catch (err: any) {
      setError(err?.message || 'Erreur lors de l\'inscription')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative min-h-full w-full overflow-hidden bg-background">
      {/* Gradient signature orange en fond */}
      <div aria-hidden="true" className="bg-signature pointer-events-none absolute inset-0" />

      <div className="relative z-10 mx-auto flex min-h-full w-full max-w-md flex-col justify-center px-6 py-10">
        {/* Logo + titre */}
        <div className="mb-8 text-center">
          <img
            src="/agon-auth.png"
            alt="AGON"
            className="mx-auto mb-5 h-24 w-24 rounded-3xl object-contain drop-shadow-[0_8px_32px_rgba(160,67,46,0.55)]"
          />
          <h1 className="text-3xl font-extrabold text-foreground tracking-wide" style={{ fontFamily: 'var(--font-display)' }}>
            {isSignup ? 'Creer un compte' : 'Bienvenue sur AGON'}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {isSignup ? 'Deja inscrit ? ' : 'Pas encore de compte ? '}
            <button
              type="button"
              className="font-semibold text-[var(--brand-cyan)] hover:text-[var(--brand-sky)] transition-colors"
              onClick={() => {
                setIsSignup(!isSignup)
                setError(null)
                loginForm.reset()
                signupForm.reset()
              }}
            >
              {isSignup ? 'Se connecter' : 'Creer mon compte'}
            </button>
          </p>
        </div>

        {/* Card glass */}
        <form
          className="glass space-y-5 rounded-2xl p-6"
          noValidate
          onSubmit={
            isSignup
              ? signupForm.handleSubmit(onSignup)
              : loginForm.handleSubmit(onLogin)
          }
        >
          {/* Email */}
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Email</label>
            <input
              {...(isSignup
                ? signupForm.register('email')
                : loginForm.register('email'))}
              type="email"
              className="block w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-foreground placeholder:text-muted-foreground focus:border-[var(--brand-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
              placeholder="votre@email.com"
              autoComplete="email"
            />
            {(isSignup
              ? signupForm.formState.errors.email
              : loginForm.formState.errors.email) && (
              <p className="mt-1 text-xs text-danger-fg">
                {(isSignup
                  ? signupForm.formState.errors.email?.message
                  : loginForm.formState.errors.email?.message)}
              </p>
            )}
          </div>

          {/* Mot de passe */}
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Mot de passe</label>
            <div className="relative">
              <input
                {...(isSignup
                  ? signupForm.register('password')
                  : loginForm.register('password'))}
                type={showPassword ? 'text' : 'password'}
                className="block w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 pr-10 text-foreground placeholder:text-muted-foreground focus:border-[var(--brand-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="••••••••"
                autoComplete={isSignup ? 'new-password' : 'current-password'}
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Masquer' : 'Afficher'}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {(isSignup
              ? signupForm.formState.errors.password
              : loginForm.formState.errors.password) && (
              <p className="mt-1 text-xs text-danger-fg">
                {(isSignup
                  ? signupForm.formState.errors.password?.message
                  : loginForm.formState.errors.password?.message)}
              </p>
            )}
          </div>

          {/* Confirmation (signup) */}
          {isSignup && (
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Confirmer le mot de passe</label>
              <input
                {...signupForm.register('confirmPassword')}
                type="password"
                className="block w-full rounded-md border border-[var(--border-subtle)] bg-[var(--surface-2)] px-3 py-2 text-foreground placeholder:text-muted-foreground focus:border-[var(--brand-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand-primary)]"
                placeholder="••••••••"
                autoComplete="new-password"
              />
              {signupForm.formState.errors.confirmPassword && (
                <p className="mt-1 text-xs text-danger-fg">
                  {signupForm.formState.errors.confirmPassword.message}
                </p>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 rounded-md border border-danger/40 bg-danger-bg p-3 text-sm text-danger-fg">
              <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="btn-glass-primary w-full"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                {isSignup ? 'Inscription...' : 'Connexion...'}
              </>
            ) : (
              isSignup ? 'Creer mon compte' : 'Se connecter'
            )}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          AGON PWA — connecte a Supabase.
        </p>
      </div>
    </div>
  )
}
