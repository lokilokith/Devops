import { useState } from "react"
import { useNavigate, useLocation, Navigate } from "react-router-dom"
import { useAuth } from "./AuthContext"
import { authService } from "@/services/auth.service"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card"
import { ShieldCheck } from "lucide-react"

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || "/dashboard"

  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [isLoading, setIsLoading] = useState(false)

  // Redirect to dashboard if already authenticated
  const { isAuthenticated, isInitializing } = useAuth()
  if (!isInitializing && isAuthenticated) {
    return <Navigate to={from} replace />
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setIsLoading(true)

    try {
      // Step 1: Authenticate — receive access token from backend
      const tokens = await authService.login({ username, password })

      // Step 2: Temporarily store the token so the Axios interceptor includes it
      localStorage.setItem("opsforge_token", tokens.access_token)

      // Step 3: Fetch the authenticated user's profile
      const userProfile = await authService.getMe()

      // Step 4: Persist token + user in AuthContext and localStorage
      login(tokens.access_token, tokens.refresh_token || "", userProfile)

      // Step 5: Redirect to the originally requested page (or dashboard)
      navigate(from, { replace: true })
    } catch (err: any) {
      // Clean up partially stored token on failure
      localStorage.removeItem("opsforge_token")
      const message =
        err.message ||
        err.response?.data?.errors?.[0] ||
        "Invalid credentials"
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex h-screen w-full items-center justify-center bg-muted/40 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <ShieldCheck className="h-10 w-10 text-primary" />
          </div>
          <CardTitle className="text-2xl">OpsForge Login</CardTitle>
          <CardDescription>Enter your credentials to access the PAM platform.</CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Input
                id="username"
                type="text"
                placeholder="Username"
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Input
                id="password"
                type="password"
                placeholder="Password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
          </CardContent>
          <CardFooter>
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? "Authenticating..." : "Sign in"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  )
}
