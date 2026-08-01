import { apiClient } from "@/api/axios"

export interface AuditLog {
  id: string
  event_type: string
  user_id: string
  ip_address: string
  details: string
  created_at: string
}

export const auditService = {
  async listLogs(params?: any): Promise<{ items: AuditLog[]; total: number }> {
    const response = await apiClient.get("/audit", { params })
    return response.data
  },
}
