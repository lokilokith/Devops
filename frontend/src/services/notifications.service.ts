import { apiClient } from "@/api/axios"

export interface Notification {
  id: string
  title: string
  message: string
  category: "success" | "warning" | "security" | "approval" | "system"
  is_read: boolean
  created_at: string
}

export const notificationsService = {
  async listNotifications(params?: any): Promise<{ items: Notification[]; total: number }> {
    const response = await apiClient.get("/notifications", { params })
    const envelope = response.data
    return {
      items: envelope.data ?? [],
      total: envelope.meta?.total ?? (envelope.data?.length ?? 0),
    }
  },

  // Backend route: PATCH /notifications/:id/read
  async markRead(id: string): Promise<void> {
    await apiClient.patch(`/notifications/${id}/read`)
  },

  // Backend route: PATCH /notifications/read-all
  async markAllRead(): Promise<void> {
    await apiClient.patch("/notifications/read-all")
  },

  async deleteNotification(id: string): Promise<void> {
    await apiClient.delete(`/notifications/${id}`)
  },
}
