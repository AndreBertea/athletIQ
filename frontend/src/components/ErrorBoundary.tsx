import React from 'react'
import * as Sentry from '@sentry/react'

interface Props {
  children: React.ReactNode
  fallback?: React.ReactNode
  sectionName?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    Sentry.captureException(error, { extra: { componentStack: errorInfo.componentStack } })
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback
      }

      if (this.props.sectionName) {
        return (
          <div className="flex items-center justify-center py-12">
            <div className="text-center max-w-md px-6">
              <div className="text-4xl mb-3">⚠️</div>
              <h2 className="text-lg font-semibold text-gray-900 mb-2">
                Erreur dans {this.props.sectionName}
              </h2>
              <p className="text-gray-500 mb-4 text-sm">
                Cette section a rencontré un problème. Vous pouvez réessayer ou recharger la page.
              </p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={this.handleReset}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors text-sm"
                >
                  Réessayer
                </button>
                <button
                  onClick={() => window.location.reload()}
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors text-sm"
                >
                  Recharger la page
                </button>
              </div>
              {this.state.error && (
                <p className="mt-4 text-xs text-gray-400 break-words">
                  Détail : {this.state.error.message}
                </p>
              )}
            </div>
          </div>
        )
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="text-center max-w-md px-6">
            <div className="text-5xl mb-4">⚠️</div>
            <h1 className="text-xl font-semibold text-gray-900 mb-2">
              Une erreur inattendue est survenue
            </h1>
            <p className="text-gray-500 mb-6">
              L'application a rencontré un problème. Vous pouvez essayer de recharger la page.
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={this.handleReset}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
              >
                Réessayer
              </button>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
              >
                Recharger la page
              </button>
            </div>
            {this.state.error && (
              <p className="mt-6 text-xs text-gray-400 break-words">
                Détail : {this.state.error.message}
              </p>
            )}
          </div>
        </div>
      )
    }

    return this.props.children
  }
}

export default ErrorBoundary
