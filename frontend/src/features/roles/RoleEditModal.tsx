import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { rolesService, Role, RolePatchPayload } from "@/services/roles.service"
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

interface RoleEditModalProps {
  role: Role | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function RoleEditModal({ role, open, onOpenChange }: RoleEditModalProps) {
  const [formData, setFormData] = React.useState<RolePatchPayload>({
    role_name: "",
    description: "",
    status: "active",
  })
  const queryClient = useQueryClient()
  const { toast } = useToast()

  // Sync form with selected role when modal opens
  React.useEffect(() => {
    if (role && open) {
      setFormData({
        role_name: role.role_name,
        description: role.description || "",
        status: role.status || "active",
      })
    }
  }, [role, open])

  const updateMutation = useMutation({
    mutationFn: (data: RolePatchPayload) => {
      if (!role) throw new Error("No role selected")
      return rolesService.patchRole(role.id, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["roles"] })
      toast({ title: "Success", description: "Role updated successfully." })
      onOpenChange(false)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description:
          error.response?.data?.message ||
          error.response?.data?.errors?.[0] ||
          "Failed to update role.",
        variant: "destructive",
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateMutation.mutate(formData)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Edit Role</DialogTitle>
          <DialogDescription>
            Update details for role <strong>{role?.role_code}</strong>.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="edit-role-code" className="text-sm font-medium text-muted-foreground">
              Role Code (read-only)
            </label>
            <Input
              id="edit-role-code"
              value={role?.role_code || ""}
              disabled
              className="opacity-60"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="edit-role-name" className="text-sm font-medium">
              Role Name <span className="text-destructive">*</span>
            </label>
            <Input
              id="edit-role-name"
              name="role_name"
              value={formData.role_name || ""}
              onChange={handleChange}
              placeholder="Role name"
              required
              minLength={3}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="edit-role-description" className="text-sm font-medium">
              Description
            </label>
            <Input
              id="edit-role-description"
              name="description"
              value={formData.description || ""}
              onChange={handleChange}
              placeholder="Role description"
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="edit-role-status" className="text-sm font-medium">
              Status
            </label>
            <Select
              value={formData.status}
              onValueChange={(val) => setFormData((prev) => ({ ...prev, status: val }))}
            >
              <SelectTrigger id="edit-role-status">
                <SelectValue placeholder="Select status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="inactive">Inactive</SelectItem>
                <SelectItem value="retired">Retired</SelectItem>
              </SelectContent>
            </Select>
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
