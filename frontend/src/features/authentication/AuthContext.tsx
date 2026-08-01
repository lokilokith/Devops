import { createContext, useContext, useState, useEffect, useCallback } from "react"
import { authService } from "@/services/auth.service"
import { router } from "@/routes"
import { useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"

// Matches exactly what GET /auth/me returns
export interface User {
  id: string
  username: string
  email: string
  full_name: string
  roles: string[]
  permissions: string[]
}

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isInitializing: boolean
  token: string | null
  login: (token: string, refreshToken: string, user: User) => void
  logout: () => void
  hasRole: (role: string) => boolean
  hasPermission: (permission: string) => boolean
  hasAnyPermission: (permissions: string[]) => boolean
  hasAllPermissions: (permissions: string[]) => boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [isInitializing, setIsInitializing] = useState(true)
  const queryClient = useQueryClient()

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    localStorage.removeItem("opsforge_token")
    localStorage.removeItem("opsforge_refresh_token")
    localStorage.removeItem("opsforge_user")
    
    // Clear query cache to prevent stale data
    queryClient.clear()
    
    router.navigate("/login", { replace: true })
  }, [queryClient])

  useEffect(() => {
    const handleLogoutEvent = () => logout();
    window.addEventListener('auth:logout', handleLogoutEvent);
    return () => window.removeEventListener('auth:logout', handleLogoutEvent);
  }, [logout]);

  useEffect(() => {
    const restoreSession = async () => {
      const storedToken = localStorage.getItem("opsforge_token")
      const storedRefresh = localStorage.getItem("opsforge_refresh_token")

      if (storedToken && storedRefresh) {
        try {
          const fetchedUser = await authService.getMe()
          setToken(storedToken)
          setUser(fetchedUser)
        } catch (error) {
          // If it fails (and interceptor refresh also fails), interceptor will trigger logout.
          setToken(null)
          setUser(null)
        }
      } else {
        setToken(null)
        setUser(null)
      }
      setIsInitializing(false)
    }

    restoreSession()
  }, [])

  const login = (newToken: string, newRefreshToken: string, newUser: User) => {
    setToken(newToken)
    setUser(newUser)
    localStorage.setItem("opsforge_token", newToken)
    localStorage.setItem("opsforge_refresh_token", newRefreshToken)
    localStorage.setItem("opsforge_user", JSON.stringify(newUser))
  }

  const hasRole = (role: string): boolean => {
    return user?.roles.includes(role) ?? false
  }

  const hasPermission = (permission: string): boolean => {
    return user?.permissions?.includes(permission) ?? false
  }

  const hasAnyPermission = (permissions: string[]): boolean => {
    return permissions.some(p => hasPermission(p))
  }

  const hasAllPermissions = (permissions: string[]): boolean => {
    return permissions.every(p => hasPermission(p))
  }

  if (isInitializing) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!token,
        isInitializing,
        token,
        login,
        logout,
        hasRole,
        hasPermission,
        hasAnyPermission,
        hasAllPermissions,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
