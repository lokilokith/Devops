import { Navigate } from "react-router-dom"
import { useAuth } from "./AuthContext"

interface RoleGuardProps {
  children: React.ReactNode
  requiredRole?: string
  fallbackUrl?: string
}

export function RoleGuard({
  children,
  requiredRole,
  fallbackUrl = "/403",
}: RoleGuardProps) {
  const { hasRole } = useAuth()

  if (requiredRole && !hasRole(requiredRole)) {
    return <Navigate to={fallbackUrl} replace />
  }

  return <>{children}</>
}
