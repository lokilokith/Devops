import { apiClient } from "@/api/axios"

export interface AccessRequest {
  id: string
  resource_name: string
  permission_name: string
  status: "pending" | "approved" | "rejected" | "cancelled" | "expired"
  reason: string
  created_at: string
}

export interface AccessRequestListParams {
  skip?: number
  limit?: number
  search?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const accessRequestsService = {
  async listRequests(params: AccessRequestListParams = {}): Promise<{ items: AccessRequest[]; total: number }> {
    const response = await apiClient.get("/access-requests", { 
      params: {
        skip: params.skip ?? 0,
        limit: params.limit ?? 10,
        search: params.search
      }
    })
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0)
    }
  },
  
  async getRequest(id: string): Promise<AccessRequest> {
    const response = await apiClient.get(`/access-requests/${id}`)
    return unwrap<AccessRequest>(response)
  },
  
  async createRequest(data: any): Promise<AccessRequest> {
    const response = await apiClient.post("/access-requests", data)
    return unwrap<AccessRequest>(response)
  },
  
  async cancelRequest(id: string): Promise<void> {
    await apiClient.post(`/access-requests/${id}/cancel`)
  },
}
