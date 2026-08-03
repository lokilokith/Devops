import { apiClient } from "@/api/axios"

export interface ApprovalWorkflow {
  id: string
  access_request_id: string
  approver_id: string
  approval_level: "manager" | "security" | "system_admin"
  status: "pending" | "approved" | "rejected" | "cancelled"
  comments?: string | null
  requested_role_name?: string | null
  requested_resource_name?: string | null
  created_at: string
  updated_at?: string
}

export interface ApprovalWorkflowListParams {
  skip?: number
  limit?: number
  status?: string
  search?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const approvalWorkflowsService = {
  async listWorkflows(params: ApprovalWorkflowListParams = {}): Promise<{ items: ApprovalWorkflow[]; total: number }> {
    const response = await apiClient.get("/approval-workflows", {
      params: {
        skip: params.skip ?? 0,
        limit: params.limit ?? 10,
        status: params.status || undefined,
        // search: params.search || undefined, // approval-workflow backend list is filtered via status only
      },
    })
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0),
    }
  },

  async getWorkflow(id: string): Promise<ApprovalWorkflow> {
    const response = await apiClient.get(`/approval-workflows/${id}`)
    return unwrap<ApprovalWorkflow>(response)
  },

  async approve(id: string, comments?: string): Promise<void> {
    await apiClient.post(`/approval-workflows/${id}/approve`, { comments: comments || "" })
  },

  // BUG-AR-03 FIX: Backend approval-workflow reject accepts `comments` (as the approval workflow route)
  // But access-request reject route requires `rejected_reason`
  // This service handles /approval-workflows/{id}/reject (which uses `comments`)
  async reject(id: string, comments?: string): Promise<void> {
    await apiClient.post(`/approval-workflows/${id}/reject`, { comments: comments || "Rejected" })
  },
}
