import { apiClient } from "@/api/axios"

export interface Resource {
  id: string
  resource_name: string
  description?: string
}

export interface ResourceListParams {
  skip?: number
  limit?: number
  search?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const resourcesService = {
  async listResources(params: ResourceListParams = {}): Promise<{ items: Resource[]; total: number }> {
    const response = await apiClient.get("/resources", { 
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
  
  async getResource(id: string): Promise<Resource> {
    const response = await apiClient.get(`/resources/${id}`)
    return unwrap<Resource>(response)
  },
  
  async createResource(data: { resource_name: string; description?: string }): Promise<Resource> {
    const response = await apiClient.post("/resources", data)
    return unwrap<Resource>(response)
  },
  
  async updateResource(id: string, data: { resource_name: string; description?: string }): Promise<Resource> {
    const response = await apiClient.put(`/resources/${id}`, data)
    return unwrap<Resource>(response)
  },
  
  async deleteResource(id: string): Promise<void> {
    await apiClient.delete(`/resources/${id}`)
  },
}
