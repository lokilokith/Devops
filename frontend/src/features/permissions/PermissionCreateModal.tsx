import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { permissionsService, CreatePermissionRequest } from "@/services/permissions.service"
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

interface PermissionCreateModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const EMPTY_FORM: CreatePermissionRequest = {
  permission_code: "",
  permission_name: "",
  description: "",
  action: "execute",
}

export function PermissionCreateModal({ open, onOpenChange }: PermissionCreateModalProps) {
  const [formData, setFormData] = React.useState<CreatePermissionRequest>(EMPTY_FORM)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  React.useEffect(() => {
    if (open) {
      setFormData(EMPTY_FORM)
    }
  }, [open])

  const createMutation = useMutation({
    mutationFn: (data: CreatePermissionRequest) => permissionsService.createPermission(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["permissions"] })
      toast({ title: "Success", description: "Permission created successfully." })
      onOpenChange(false)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description:
          error.response?.data?.message ||
          error.response?.data?.errors?.[0] ||
          "Failed to create permission.",
        variant: "destructive",
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({
      ...formData,
      permission_code: formData.permission_code.toUpperCase().replace(/\s+/g, "_"),
    })
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>Create Permission</DialogTitle>
          <DialogDescription>
            Define a new access permission.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="permission-code" className="text-sm font-medium">
              Permission Code <span className="text-destructive">*</span>
            </label>
            <Input
              id="permission-code"
              name="permission_code"
              value={formData.permission_code}
              onChange={handleChange}
              placeholder="RESOURCE_ACTION (auto-uppercased)"
              required
              minLength={3}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="permission-name" className="text-sm font-medium">
              Permission Name <span className="text-destructive">*</span>
            </label>
            <Input
              id="permission-name"
              name="permission_name"
              value={formData.permission_name}
              onChange={handleChange}
              placeholder="e.g. Read Resources"
              required
              minLength={3}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="permission-action" className="text-sm font-medium">
              Action
            </label>
            <Select
              value={formData.action}
              onValueChange={(val) => setFormData((prev) => ({ ...prev, action: val }))}
            >
              <SelectTrigger id="permission-action">
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
            <label htmlFor="permission-description" className="text-sm font-medium">
              Description
            </label>
            <Input
              id="permission-description"
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="Describe the permission..."
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create Permission"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
