import axios, { AxiosError, InternalAxiosRequestConfig } from "axios"
import { router } from "@/routes"

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api/v1"

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 10000, // 10 second timeout
})

// Request Interceptor to append JWT token
apiClient.interceptors.request.use(
  (config) => {
    // We do NOT use localStorage for access token if we can avoid it, but for compatibility 
    // across reloads, we read it. The user requested minimizing reliance on persistent access token.
    const token = localStorage.getItem("opsforge_token")
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// State for refresh queue
let isRefreshing = false
let refreshSubscribers: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = []

const subscribeTokenRefresh = (resolve: (token: string) => void, reject: (err: unknown) => void) => {
  refreshSubscribers.push({ resolve, reject })
}

const onRefreshed = (token: string) => {
  refreshSubscribers.forEach(({ resolve }) => resolve(token))
  refreshSubscribers = []
}

const onRefreshFailed = (err: unknown) => {
  refreshSubscribers.forEach(({ reject }) => reject(err))
  refreshSubscribers = []
}

// Response Interceptor for global error handling
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    if (error.response) {
      const status = error.response.status
      if (status === 401 && originalRequest && !originalRequest._retry) {
        if (isRefreshing) {
          return new Promise((resolve, reject) => {
            subscribeTokenRefresh(
              (token: string) => {
                originalRequest.headers.Authorization = `Bearer ${token}`
                resolve(apiClient(originalRequest))
              },
              (err: unknown) => reject(err)
            )
          })
        }

        originalRequest._retry = true
        isRefreshing = true

        try {
          const refreshToken = localStorage.getItem("opsforge_refresh_token")
          if (!refreshToken) {
            throw new Error("No refresh token available")
          }

          // Directly use axios so we don't trigger our own interceptors and loop
          const response = await axios.post(`${BASE_URL}/auth/refresh`, { refresh_token: refreshToken })
          const { access_token, refresh_token: new_refresh } = response.data.data

          localStorage.setItem("opsforge_token", access_token)
          if (new_refresh) {
            localStorage.setItem("opsforge_refresh_token", new_refresh)
          }

          isRefreshing = false
          onRefreshed(access_token)

          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return apiClient(originalRequest)
        } catch (refreshError) {
          isRefreshing = false
          onRefreshFailed(refreshError)
          
          localStorage.removeItem("opsforge_token")
          localStorage.removeItem("opsforge_refresh_token")
          localStorage.removeItem("opsforge_user")
          
          // Emit event to logout gracefully via Context, fallback to router navigate
          window.dispatchEvent(new Event('auth:logout'))
          router.navigate("/login", { replace: true })
          return Promise.reject(refreshError)
        }
      } else if (status === 403) {
        if (window.location.pathname !== "/403") {
          router.navigate("/403", { replace: true })
        }
      }
    } else if (error.code === 'ECONNABORTED') {
      error.message = "Request timed out. Please try again later."
    } else if (error.request) {
      error.message = "Backend unavailable. Please check your network connection."
    }
    
    // Attempt to extract centralized error message from backend response
    if (error.response?.data && typeof error.response.data === 'object') {
      const data = error.response.data as any
      if (data.message) {
        error.message = data.message
      } else if (data.error) {
        error.message = data.error
      }
    }

    return Promise.reject(error)
  }
)
