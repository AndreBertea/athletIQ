import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import Login from '../pages/Login'
import { AuthProvider } from '../contexts/AuthContext'

// Mock du service d'auth
vi.mock('../services/authService', () => ({
  authService: {
    login: vi.fn(),
    signup: vi.fn(),
    getCurrentUser: vi.fn(),
    refreshToken: vi.fn(),
    getStravaStatus: vi.fn(),
    initiateStravaLogin: vi.fn(),
  },
}))

// Helper pour render avec les providers
const renderWithProviders = (component: React.ReactElement) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          {component}
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('Login Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Mock localStorage
    const localStorageMock = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    }
    Object.defineProperty(window, 'localStorage', {
      value: localStorageMock,
      writable: true,
    })
  })

  test('renders login form by default', () => {
    renderWithProviders(<Login />)
    
    expect(screen.getByText('Connexion à AthlétIQ')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('votre@email.com')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('••••••••')).toBeInTheDocument()
    expect(screen.getByText('Se connecter')).toBeInTheDocument()
  })

  test('switches to signup form when button clicked', () => {
    renderWithProviders(<Login />)
    
    const switchButton = screen.getByText('créez un nouveau compte')
    fireEvent.click(switchButton)
    
    expect(screen.getByText('Créer un compte')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Votre nom complet')).toBeInTheDocument()
    expect(screen.getByText('Créer mon compte')).toBeInTheDocument()
  })

  test('validates email format', async () => {
    renderWithProviders(<Login />)
    
    const emailInput = screen.getByPlaceholderText('votre@email.com')
    const passwordInput = screen.getByPlaceholderText('••••••••')
    const submitButton = screen.getByText('Se connecter')
    
    fireEvent.change(emailInput, { target: { value: 'invalid-email' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(screen.getByText('Email invalide')).toBeInTheDocument()
    })
  })

  test('validates password length', async () => {
    renderWithProviders(<Login />)
    
    const emailInput = screen.getByPlaceholderText('votre@email.com')
    const passwordInput = screen.getByPlaceholderText('••••••••')
    const submitButton = screen.getByText('Se connecter')
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: '12345' } })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(screen.getByText('Le mot de passe doit contenir au moins 6 caractères')).toBeInTheDocument()
    })
  })

  test('validates password confirmation in signup', async () => {
    renderWithProviders(<Login />)
    
    // Switch to signup
    fireEvent.click(screen.getByText('créez un nouveau compte'))
    
    const emailInput = screen.getByPlaceholderText('votre@email.com')
    const nameInput = screen.getByPlaceholderText('Votre nom complet')
    const passwordInputs = screen.getAllByPlaceholderText('••••••••')
    const submitButton = screen.getByText('Créer mon compte')
    
    fireEvent.change(nameInput, { target: { value: 'Test User' } })
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInputs[0], { target: { value: 'password123' } })
    fireEvent.change(passwordInputs[1], { target: { value: 'differentpassword' } })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(screen.getByText('Les mots de passe ne correspondent pas')).toBeInTheDocument()
    })
  })

  test('toggles password visibility', () => {
    renderWithProviders(<Login />)
    
    const passwordInput = screen.getByPlaceholderText('••••••••')
    const toggleButton = screen.getByRole('button', { name: '' }) // L'icône eye
    
    expect(passwordInput).toHaveAttribute('type', 'password')
    
    fireEvent.click(toggleButton)
    expect(passwordInput).toHaveAttribute('type', 'text')
    
    fireEvent.click(toggleButton)
    expect(passwordInput).toHaveAttribute('type', 'password')
  })

  test('displays loading state during submission', async () => {
    const { authService } = await import('../services/authService')
    
    // Mock une promesse qui ne se résout pas
    vi.mocked(authService.login).mockImplementation(() => new Promise(() => {}))
    
    renderWithProviders(<Login />)
    
    const emailInput = screen.getByPlaceholderText('votre@email.com')
    const passwordInput = screen.getByPlaceholderText('••••••••')
    const submitButton = screen.getByText('Se connecter')
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(submitButton)
    
    await waitFor(() => {
      expect(screen.getByText('Connexion...')).toBeInTheDocument()
      expect(submitButton).toBeDisabled()
    })
  })
}) 