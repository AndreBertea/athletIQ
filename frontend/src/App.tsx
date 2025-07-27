import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Calendar } from 'lucide-react'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Activities from './pages/Activities'
import WorkoutPlans from './pages/WorkoutPlans'
import DetailedData from './pages/DetailedData'
import StravaConnect from './pages/StravaConnect'
import GoogleConnect from './pages/GoogleConnect'
import Layout from './components/Layout'

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
    <AuthProvider>
      <div className="min-h-screen bg-gray-50">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout>
                  <Dashboard />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/activites"
            element={
              <ProtectedRoute>
                <Layout>
                  <Activities />
                </Layout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/plans"
            element={
              <ProtectedRoute>
                <Layout>
                  <WorkoutPlans />
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
          {/* Redirections pour compatibilité */}
          <Route path="/activities" element={<Navigate to="/activites" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </AuthProvider>
  )
}

export default App 