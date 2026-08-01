import { apiClient } from "@/api/axios"

export interface LoginCredentials {
  username: string
  password: string
}

export interface AuthTokenResponse {
  access_token: string
  refresh_token?: string
  token_type: string
  expires_in: number
}

export const authService = {
  /**
   * Authenticate with username and password.
   * Returns the raw token data from the backend.
   * The caller is responsible for fetching /auth/me to hydrate the user profile.
   */
  async login(credentials: LoginCredentials): Promise<AuthTokenResponse> {
    const response = await apiClient.post("/auth/login", credentials)
    // Backend envelope: { success, message, data: { access_token, refresh_token, token_type, expires_in } }
    return response.data.data
  },

  async logout(): Promise<void> {
    await apiClient.post("/auth/logout")
  },

  async refresh(refreshToken: string): Promise<AuthTokenResponse> {
    const response = await apiClient.post("/auth/refresh", { refresh_token: refreshToken })
    return response.data.data
  },

  async getMe(): Promise<{
    id: string
    username: string
    email: string
    full_name: string
    roles: string[]
  }> {
    const response = await apiClient.get("/auth/me")
    // Backend envelope: { success, message, data: { id, username, email, full_name, roles } }
    return response.data.data
  },
}
