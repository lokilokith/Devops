import { apiClient } from "@/api/axios"

export interface Role {
  id: string
  role_name: string
  description?: string
  permissions?: string[]
}

export interface RoleListParams {
  skip?: number
  limit?: number
  search?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const rolesService = {
  async listRoles(params: RoleListParams = {}): Promise<{ items: Role[]; total: number }> {
    const response = await apiClient.get("/roles", { 
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
  
  async getRole(id: string): Promise<Role> {
    const response = await apiClient.get(`/roles/${id}`)
    return unwrap<Role>(response)
  },
  
  async createRole(data: { role_name: string; description?: string }): Promise<Role> {
    const response = await apiClient.post("/roles", data)
    return unwrap<Role>(response)
  },
  
  async updateRole(id: string, data: { role_name: string; description?: string }): Promise<Role> {
    const response = await apiClient.put(`/roles/${id}`, data)
    return unwrap<Role>(response)
  },
  
  async deleteRole(id: string): Promise<void> {
    await apiClient.delete(`/roles/${id}`)
  },
}
