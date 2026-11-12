import { apiClient } from "@/api/axios"

export interface JITAccessGrant {
  id: string
  user_id: string
  role_id: string
  resource_id: string
  target_account_binding_id: string | null
  command_set_id: string | null
  approved_by: string | null
  approval_request_id: string
  status: string
  created_at: string
  activated_at: string | null
  expires_at: string | null
  revoked_at: string | null
  revocation_start: string | null
  revocation_complete: string | null
}

export const jitService = {
  getCurrentSessions: async (): Promise<JITAccessGrant[]> => {
    // Current active/pending grants
    const response = await apiClient.get("/jit/session/current")
    return response.data
  },
  
  listGrants: async (): Promise<{items: JITAccessGrant[], total: number}> => {
    // List all grants (to see terminated ones too)
    const response = await apiClient.get("/jit/grants")
    return response.data
  },

  activateGrant: async (grantId: string): Promise<JITAccessGrant> => {
    const response = await apiClient.post(`/jit/${grantId}/activate`)
    return response.data
  },

  terminateSessions: async (grantId: string): Promise<{ terminated_count: number }> => {
    // Terminate sessions / revoke grant
    const response = await apiClient.post(`/jit/${grantId}/terminate-sessions`)
    return response.data
  }
}
