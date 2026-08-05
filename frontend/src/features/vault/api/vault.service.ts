import { apiClient } from "@/api/axios"
import { VaultSecret, SecretRevealResponse, VaultStats } from "../types"

export const vaultService = {
  getSecrets: async (): Promise<VaultSecret[]> => {
    const response = await apiClient.get("/vault/secrets")
    return response.data.data
  },

  getStats: async (): Promise<VaultStats> => {
    // If backend provides a specific endpoint for stats, use it.
    // Otherwise, we calculate from the secrets list.
    try {
      const response = await apiClient.get("/vault/secrets/stats")
      return response.data.data
    } catch (e) {
      // Fallback: fetch all and calculate (temporary for UI stubbing if no stats endpoint)
      const secrets = await vaultService.getSecrets()
      return {
        total: secrets.length,
        active: secrets.filter((s) => s.status === "active").length,
        disabled: secrets.filter((s) => s.status === "disabled").length,
      }
    }
  },

  createSecret: async (data: { resource_id: string; payload: string }): Promise<VaultSecret> => {
    const response = await apiClient.post("/vault/secrets", data)
    return response.data.data
  },

  retrieveSecret: async (secretId: string): Promise<SecretRevealResponse> => {
    const response = await apiClient.post(`/vault/secrets/${secretId}/retrieve`)
    return response.data.data
  },

  disableSecret: async (secretId: string): Promise<VaultSecret> => {
    const response = await apiClient.post(`/vault/secrets/${secretId}/disable`)
    return response.data.data
  },

  rotateSecret: async (secretId: string, data: { payload: string }): Promise<VaultSecret> => {
    const response = await apiClient.post(`/vault/secrets/${secretId}/rotate`, data)
    return response.data.data
  },
}
