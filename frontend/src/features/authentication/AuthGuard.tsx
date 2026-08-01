import { Navigate } from "react-router-dom"
import { useAuth } from "./AuthContext"

interface AuthGuardProps {
  children: React.ReactNode
  requiredPermission?: string
  requiredPermissions?: string[]
  fallbackUrl?: string
}

export function AuthGuard({
  children,
  requiredPermission,
  requiredPermissions,
  fallbackUrl = "/403",
}: AuthGuardProps) {
  const { hasPermission, hasAllPermissions } = useAuth()

  if (requiredPermission && !hasPermission(requiredPermission)) {
    return <Navigate to={fallbackUrl} replace />
  }

  if (requiredPermissions && !hasAllPermissions(requiredPermissions)) {
    return <Navigate to={fallbackUrl} replace />
  }

  return <>{children}</>
}
