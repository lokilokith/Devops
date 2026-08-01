import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useAuth } from "./AuthContext"

export function ProtectedRoute() {
  const { isAuthenticated, isInitializing } = useAuth()
  const location = useLocation()

  if (isInitializing) {
    // AuthContext handles rendering the loader globally, but just in case
    return null
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}
