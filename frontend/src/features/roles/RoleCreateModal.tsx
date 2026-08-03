import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { rolesService, RoleCreatePayload } from "@/services/roles.service"
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

interface RoleCreateModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const EMPTY_FORM: RoleCreatePayload = {
  role_code: "",
  role_name: "",
  description: "",
  role_type: "custom",
}

export function RoleCreateModal({ open, onOpenChange }: RoleCreateModalProps) {
  const [formData, setFormData] = React.useState<RoleCreatePayload>(EMPTY_FORM)
  const queryClient = useQueryClient()
  const { toast } = useToast()

  // Reset form when modal opens
  React.useEffect(() => {
    if (open) {
      setFormData(EMPTY_FORM)
    }
  }, [open])

  const createMutation = useMutation({
    mutationFn: (data: RoleCreatePayload) => rolesService.createRole(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["roles"] })
      toast({ title: "Success", description: "Role created successfully." })
      onOpenChange(false)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description:
          error.response?.data?.message ||
          error.response?.data?.errors?.[0] ||
          "Failed to create role.",
        variant: "destructive",
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // role_code must be uppercase: enforce at submit time
    createMutation.mutate({
      ...formData,
      role_code: formData.role_code.toUpperCase().replace(/\s+/g, "_"),
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
          <DialogTitle>Create Role</DialogTitle>
          <DialogDescription>
            Define a new authorization role for the system.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <label htmlFor="role-code" className="text-sm font-medium">
              Role Code <span className="text-destructive">*</span>
            </label>
            <Input
              id="role-code"
              name="role_code"
              value={formData.role_code}
              onChange={handleChange}
              placeholder="ADMIN_READONLY (auto-uppercased)"
              required
              minLength={3}
            />
            <p className="text-xs text-muted-foreground">
              Unique identifier. Uppercase letters, numbers, and underscores only.
            </p>
          </div>
          <div className="space-y-2">
            <label htmlFor="role-name" className="text-sm font-medium">
              Role Name <span className="text-destructive">*</span>
            </label>
            <Input
              id="role-name"
              name="role_name"
              value={formData.role_name}
              onChange={handleChange}
              placeholder="Read-Only Administrator"
              required
              minLength={3}
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="role-type" className="text-sm font-medium">
              Role Type
            </label>
            <Select
              value={formData.role_type}
              onValueChange={(val) => setFormData((prev) => ({ ...prev, role_type: val }))}
            >
              <SelectTrigger id="role-type">
                <SelectValue placeholder="Select type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="custom">Custom</SelectItem>
                <SelectItem value="system">System</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <label htmlFor="role-description" className="text-sm font-medium">
              Description
            </label>
            <Input
              id="role-description"
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="Describe the purpose of this role..."
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
              {createMutation.isPending ? "Creating..." : "Create Role"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
