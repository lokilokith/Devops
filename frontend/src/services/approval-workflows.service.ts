import { apiClient } from "@/api/axios"

export interface ApprovalWorkflow {
  id: string
  access_request_id: string
  approver_id: string
  status: "pending" | "approved" | "rejected" | "cancelled"
  comments?: string
  created_at: string
}

export interface ApprovalWorkflowListParams {
  skip?: number
  limit?: number
  status?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const approvalWorkflowsService = {
  async listWorkflows(params: ApprovalWorkflowListParams = {}): Promise<{ items: ApprovalWorkflow[]; total: number }> {
    const response = await apiClient.get("/approval-workflows", { 
      params: {
        skip: params.skip ?? 0,
        limit: params.limit ?? 10,
        status: params.status
      }
    })
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0)
    }
  },
  
  async getWorkflow(id: string): Promise<ApprovalWorkflow> {
    const response = await apiClient.get(`/approval-workflows/${id}`)
    return unwrap<ApprovalWorkflow>(response)
  },
  
  async approve(id: string, comments?: string): Promise<void> {
    await apiClient.post(`/approval-workflows/${id}/approve`, { comments })
  },

  async reject(id: string, comments?: string): Promise<void> {
    await apiClient.post(`/approval-workflows/${id}/reject`, { comments })
  },
}
