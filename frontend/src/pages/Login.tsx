import { useState } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useAuth } from '../contexts/AuthContext'
import { Eye, EyeOff, AlertCircle } from 'lucide-react'

const loginSchema = z.object({
  email: z.string().email('Email invalide'),
  password: z.string().min(6, 'Le mot de passe doit contenir au moins 6 caractères'),
})

const signupSchema = loginSchema.extend({
  fullName: z.string().min(2, 'Le nom doit contenir au moins 2 caractères'),
  confirmPassword: z.string(),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Les mots de passe ne correspondent pas",
  path: ["confirmPassword"],
})

type LoginFormData = z.infer<typeof loginSchema>
type SignupFormData = z.infer<typeof signupSchema>

export default function Login() {
  const [isSignup, setIsSignup] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  
  const { user, login, signup } = useAuth()
  const navigate = useNavigate()

  const loginForm = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  })

  const signupForm = useForm<SignupFormData>({
    resolver: zodResolver(signupSchema),
  })

  // Rediriger si déjà connecté
  if (user) {
    return <Navigate to="/" replace />
  }

  const onLoginSubmit = async (data: LoginFormData) => {
    setLoading(true)
    setError('')
    
    try {
      await login(data.email, data.password)
      navigate('/')
    } catch (err: any) {
      // Gérer les erreurs de validation Pydantic
      if (err.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          // Erreurs de validation multiples
          const errorMessages = err.response.data.detail.map((e: any) => e.msg).join(', ')
          setError(errorMessages)
        } else {
          // Erreur simple
          setError(err.response.data.detail)
        }
      } else {
        setError('Erreur de connexion')
      }
    } finally {
      setLoading(false)
    }
  }

  const onSignupSubmit = async (data: SignupFormData) => {
    setLoading(true)
    setError('')
    
    try {
      await signup(data.email, data.password, data.fullName)
      navigate('/')
    } catch (err: any) {
      // Gérer les erreurs de validation Pydantic
      if (err.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          // Erreurs de validation multiples
          const errorMessages = err.response.data.detail.map((e: any) => e.msg).join(', ')
          setError(errorMessages)
        } else {
          // Erreur simple
          setError(err.response.data.detail)
        }
      } else {
        setError('Erreur lors de l\'inscription')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        {/* Header */}
        <div>
          <div className="mx-auto h-12 w-12 bg-primary-600 rounded-full flex items-center justify-center">
            <span className="text-white font-bold text-xl">A</span>
          </div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            {isSignup ? 'Créer un compte' : 'Connexion à AthlétIQ'}
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            {isSignup ? 'Ou ' : 'Ou '}
            <button
              type="button"
              className="font-medium text-primary-600 hover:text-primary-500"
              onClick={() => {
                setIsSignup(!isSignup)
                setError('')
                loginForm.reset()
                signupForm.reset()
              }}
            >
              {isSignup ? 'connectez-vous à votre compte existant' : 'créez un nouveau compte'}
            </button>
          </p>
        </div>

        {/* Form */}
        <form
          className="mt-8 space-y-6"
          onSubmit={isSignup ? signupForm.handleSubmit(onSignupSubmit) : loginForm.handleSubmit(onLoginSubmit)}
        >
          <div className="space-y-4">
            {/* Nom complet (signup only) */}
            {isSignup && (
              <div>
                <label className="label">Nom complet</label>
                <input
                  {...signupForm.register('fullName')}
                  type="text"
                  className="input"
                  placeholder="Votre nom complet"
                />
                {signupForm.formState.errors.fullName && (
                  <p className="error">{signupForm.formState.errors.fullName.message}</p>
                )}
              </div>
            )}

            {/* Email */}
            <div>
              <label className="label">Email</label>
              <input
                {...(isSignup ? signupForm.register('email') : loginForm.register('email'))}
                type="email"
                className="input"
                placeholder="votre@email.com"
              />
              {(isSignup ? signupForm.formState.errors.email : loginForm.formState.errors.email) && (
                <p className="error">
                  {(isSignup ? signupForm.formState.errors.email?.message : loginForm.formState.errors.email?.message)}
                </p>
              )}
            </div>

            {/* Mot de passe */}
            <div>
              <label className="label">Mot de passe</label>
              <div className="relative">
                <input
                  {...(isSignup ? signupForm.register('password') : loginForm.register('password'))}
                  type={showPassword ? 'text' : 'password'}
                  className="input pr-10"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-0 pr-3 flex items-center"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? (
                    <EyeOff className="h-5 w-5 text-gray-400" />
                  ) : (
                    <Eye className="h-5 w-5 text-gray-400" />
                  )}
                </button>
              </div>
              {(isSignup ? signupForm.formState.errors.password : loginForm.formState.errors.password) && (
                <p className="error">
                  {(isSignup ? signupForm.formState.errors.password?.message : loginForm.formState.errors.password?.message)}
                </p>
              )}
            </div>

            {/* Confirmation mot de passe (signup only) */}
            {isSignup && (
              <div>
                <label className="label">Confirmer le mot de passe</label>
                <input
                  {...signupForm.register('confirmPassword')}
                  type="password"
                  className="input"
                  placeholder="••••••••"
                />
                {signupForm.formState.errors.confirmPassword && (
                  <p className="error">{signupForm.formState.errors.confirmPassword.message}</p>
                )}
              </div>
            )}
          </div>

          {/* Error message */}
          {error && (
            <div className="rounded-md bg-red-50 p-4">
              <div className="flex">
                <AlertCircle className="h-5 w-5 text-red-400" />
                <div className="ml-3">
                  <p className="text-sm text-red-800">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Submit button */}
          <div>
            <button
              type="submit"
              disabled={loading}
              className="w-full btn-primary py-3 text-base font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? (
                <div className="flex items-center justify-center">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                  {isSignup ? 'Inscription...' : 'Connexion...'}
                </div>
              ) : (
                isSignup ? 'Créer mon compte' : 'Se connecter'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
} 