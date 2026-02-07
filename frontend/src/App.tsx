import React, { Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Calendar } from 'lucide-react'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ToastProvider } from './contexts/ToastContext'
import ErrorBoundary from './components/ErrorBoundary'
import Login from './pages/Login'
import Layout from './components/Layout'

const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const Activities = React.lazy(() => import('./pages/Activities'))
const WorkoutPlans = React.lazy(() => import('./pages/WorkoutPlans'))
const DetailedData = React.lazy(() => import('./pages/DetailedData'))
const StravaConnect = React.lazy(() => import('./pages/StravaConnect'))
const GoogleConnect = React.lazy(() => import('./pages/GoogleConnect'))
const GarminConnect = React.lazy(() => import('./pages/GarminConnect'))

// Protected Route wrapper
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-500"></div>
      </div>
    )
  }
  
  return user ? <>{children}</> : <Navigate to="/login" replace />
}

function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
      <AuthProvider>
        <div className="min-h-screen bg-gray-50">
          <Suspense fallback={
            <div className="min-h-screen flex items-center justify-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-500"></div>
            </div>
          }>
          <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout>
                  <ErrorBoundary sectionName="Tableau de bord">
                    <Dashboard />
                  </ErrorBoundary>
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/activites"
            element={
              <ProtectedRoute>
                <Layout>
                  <ErrorBoundary sectionName="Activités">
                    <Activities />
                  </ErrorBoundary>
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/plans"
            element={
              <ProtectedRoute>
                <Layout>
                  <ErrorBoundary sectionName="Plans d'entraînement">
                    <WorkoutPlans />
                  </ErrorBoundary>
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/strava-connect/donnees-detaillees"
            element={
              <ProtectedRoute>
                <Layout>
                  <DetailedData />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/plans"
            element={
              <ProtectedRoute>
                <Layout>
                  <div className="text-center py-12">
                    <Calendar className="mx-auto h-12 w-12 text-gray-400" />
                    <h3 className="mt-2 text-lg font-medium text-gray-900">Plans d'entraînement</h3>
                    <p className="mt-1 text-sm text-gray-500">
                      Cette fonctionnalité sera bientôt disponible.
                    </p>
                  </div>
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/strava-connect"
            element={
              <ProtectedRoute>
                <Layout>
                  <StravaConnect />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/google-connect"
            element={
              <ProtectedRoute>
                <Layout>
                  <GoogleConnect />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/garmin-connect"
            element={
              <ProtectedRoute>
                <Layout>
                  <GarminConnect />
                </Layout>
              </ProtectedRoute>
            }
          />
          {/* Redirections pour compatibilité */}
          <Route path="/activities" element={<Navigate to="/activites" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
          </Suspense>
      </div>
      </AuthProvider>
      </ToastProvider>
    </ErrorBoundary>
  )
}

export default App 