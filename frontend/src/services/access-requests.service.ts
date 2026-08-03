import { apiClient } from "@/api/axios"

// BUG-AR-06 FIX: Matches backend access_requests/schemas.py access_request_response_model
export interface AccessRequest {
  id: string
  request_number: string
  requester_id: string
  requested_role_id?: string | null
  requested_resource_id?: string | null
  business_justification: string
  status: "pending" | "approved" | "rejected" | "cancelled" | "expired"
  priority: "low" | "medium" | "high" | "critical"
  requested_start?: string | null
  requested_end?: string | null
  approved_by?: string | null
  approved_at?: string | null
  rejected_reason?: string | null
  created_at: string
  updated_at: string
}

export interface AccessRequestListParams {
  skip?: number
  limit?: number
  search?: string
  status?: string
}

export interface AccessRequestCreatePayload {
  business_justification: string
  requested_role_id?: string
  requested_resource_id?: string
  priority?: "low" | "medium" | "high" | "critical"
  requested_start?: string
  requested_end?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const accessRequestsService = {
  async listRequests(params: AccessRequestListParams = {}): Promise<{ items: AccessRequest[]; total: number }> {
    const response = await apiClient.get("/access-requests", {
      params: {
        skip: params.skip ?? 0,
        limit: params.limit ?? 10,
        search: params.search || undefined,
        status: params.status || undefined,
      },
    })
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0),
    }
  },

  async getRequest(id: string): Promise<AccessRequest> {
    const response = await apiClient.get(`/access-requests/${id}`)
    return unwrap<AccessRequest>(response)
  },

  async createRequest(data: AccessRequestCreatePayload): Promise<AccessRequest> {
    const response = await apiClient.post("/access-requests", data)
    return unwrap<AccessRequest>(response)
  },

  async cancelRequest(id: string): Promise<void> {
    await apiClient.post(`/access-requests/${id}/cancel`)
  },

  // Direct approve/reject on access requests (used by access_requests routes, not approval_workflow routes)
  async approveRequest(id: string): Promise<AccessRequest> {
    const response = await apiClient.post(`/access-requests/${id}/approve`)
    return unwrap<AccessRequest>(response)
  },

  // BUG-AR-03 FIX: Backend requires `rejected_reason`, not `comments`
  async rejectRequest(id: string, rejected_reason: string): Promise<AccessRequest> {
    const response = await apiClient.post(`/access-requests/${id}/reject`, { rejected_reason })
    return unwrap<AccessRequest>(response)
  },
}
