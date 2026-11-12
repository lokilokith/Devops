import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { RouterProvider } from "react-router-dom"
import { ThemeProvider } from "@/components/theme-provider"
import { AuthProvider } from "@/features/authentication/AuthContext"
import { router } from "@/routes"
import { Toaster } from "@/components/ui/toaster"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1, // Only retry once on failure
      refetchOnWindowFocus: false, // Don't refetch on window focus globally unless overridden
      staleTime: 5 * 60 * 1000, // 5 minutes stale time
    },
    mutations: {
      retry: 0, // Never retry mutations
    }
  },
})

function App() {
  return (
    <ThemeProvider defaultTheme="system" storageKey="opsforge-theme" attribute="class">
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
          <Toaster />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}

export default App
