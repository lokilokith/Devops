import { apiClient } from "@/api/axios"

// Matches backend identity/schemas.py user_model
export interface User {
  id: string
  employee_id: string
  username: string
  email: string
  full_name: string
  title?: string
  status: "active" | "suspended" | "locked" | "disabled" | "archived"
  last_login_at?: string
}

export interface UserListParams {
  skip?: number
  limit?: number
  search?: string
}

export interface UserCreatePayload {
  employee_id: string
  username: string
  email: string
  full_name: string
  password: string
  title?: string
  manager_user_id?: string
}

export interface UserUpdatePayload {
  full_name: string
  title?: string
  status: string
}

export interface UserPatchPayload {
  full_name?: string
  title?: string
  status?: string
}

const unwrap = <T>(response: any): T => response.data.data

export const usersService = {
  async listUsers(params: UserListParams = {}): Promise<{ items: User[]; total: number }> {
    // Backend uses skip/limit (offset-based)
    const response = await apiClient.get("/users", {
      params: {
        skip: params.skip ?? 0,
        limit: params.limit ?? 10,
        search: params.search,
      },
    })
    // Backend envelope: { success, message, data: [...users], meta: {...} }
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0),
    }
  },

  async getUser(id: string): Promise<User> {
    const response = await apiClient.get(`/users/${id}`)
    return unwrap<User>(response)
  },

  async createUser(data: UserCreatePayload): Promise<User> {
    const response = await apiClient.post("/users", data)
    return unwrap<User>(response)
  },

  async updateUser(id: string, data: UserUpdatePayload): Promise<User> {
    const response = await apiClient.put(`/users/${id}`, data)
    return unwrap<User>(response)
  },

  async patchUser(id: string, data: UserPatchPayload): Promise<User> {
    const response = await apiClient.patch(`/users/${id}`, data)
    return unwrap<User>(response)
  },

  async deleteUser(id: string): Promise<void> {
    await apiClient.delete(`/users/${id}`)
  },

  async lockUser(id: string): Promise<User> {
    const response = await apiClient.post(`/users/${id}/lock`)
    return unwrap<User>(response)
  },

  async unlockUser(id: string): Promise<User> {
    const response = await apiClient.post(`/users/${id}/unlock`)
    return unwrap<User>(response)
  },
}
