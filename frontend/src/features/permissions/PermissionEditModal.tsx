import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { permissionsService, Permission, UpdatePermissionRequest } from "@/services/permissions.service"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useToast } from "@/hooks/use-toast"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface PermissionEditModalProps {
  permission: Permission | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function PermissionEditModal({ permission, open, onOpenChange }: PermissionEditModalProps) {
  const [formData, setFormData] = React.useState<UpdatePermissionRequest>({})
  const queryClient = useQueryClient()
  const { toast } = useToast()

  React.useEffect(() => {
    if (open && permission) {
      setFormData({
        permission_name: permission.permission_name,
        description: permission.description || "",
        action: permission.action,
        status: permission.status,
      })
    }
  }, [open, permission])

  const updateMutation = useMutation({
    mutationFn: (data: UpdatePermissionRequest) => {
      if (!permission) throw new Error("No permission selected")
      return permissionsService.updatePermission(permission.id, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["permissions"] })
      toast({ title: "Success", description: "Permission updated successfully." })
      onOpenChange(false)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description:
          error.response?.data?.message ||
          error.response?.data?.errors?.[0] ||
          "Failed to update permission.",
        variant: "destructive",
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateMutation.mutate(formData)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Edit Permission</DialogTitle>
          <DialogDescription>
            Modify {permission?.permission_code} details.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="edit-permission-code" className="text-sm font-medium">
              Permission Code
            </label>
            <Input
              id="edit-permission-code"
              value={permission?.permission_code || ""}
              disabled
              className="bg-muted"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="edit-permission-name" className="text-sm font-medium">
              Permission Name <span className="text-destructive">*</span>
            </label>
            <Input
              id="edit-permission-name"
              name="permission_name"
              value={formData.permission_name || ""}
              onChange={handleChange}
              required
              minLength={3}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="edit-permission-action" className="text-sm font-medium">
              Action
            </label>
            <Select
              value={formData.action}
              onValueChange={(val) => setFormData((prev) => ({ ...prev, action: val }))}
            >
              <SelectTrigger id="edit-permission-action">
                <SelectValue placeholder="Select action" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="create">Create</SelectItem>
                <SelectItem value="read">Read</SelectItem>
                <SelectItem value="update">Update</SelectItem>
                <SelectItem value="delete">Delete</SelectItem>
                <SelectItem value="execute">Execute</SelectItem>
                <SelectItem value="manage">Manage</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <label htmlFor="edit-permission-status" className="text-sm font-medium">
              Status
            </label>
            <Select
              value={formData.status}
              onValueChange={(val) => setFormData((prev) => ({ ...prev, status: val }))}
            >
              <SelectTrigger id="edit-permission-status">
                <SelectValue placeholder="Select status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="inactive">Inactive</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <label htmlFor="edit-permission-description" className="text-sm font-medium">
              Description
            </label>
            <Input
              id="edit-permission-description"
              name="description"
              value={formData.description || ""}
              onChange={handleChange}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={updateMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
