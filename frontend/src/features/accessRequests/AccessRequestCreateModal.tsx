import * as React from "react"
import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query"
import { accessRequestsService, AccessRequestCreatePayload } from "@/services/access-requests.service"
import { rolesService } from "@/services/roles.service"
import { resourcesService } from "@/services/resources.service"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useToast } from "@/hooks/use-toast"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

interface AccessRequestCreateModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialType?: "role" | "resource"
  initialResourceId?: string
}

export function AccessRequestCreateModal({ open, onOpenChange, initialType = "role", initialResourceId }: AccessRequestCreateModalProps) {
  const [formData, setFormData] = React.useState<AccessRequestCreatePayload>({
    business_justification: "",
    priority: "low",
    requested_resource_id: initialResourceId,
  })
  
  const [requestType, setRequestType] = React.useState<"role" | "resource">(initialType)

  React.useEffect(() => {
    if (open) {
      setRequestType(initialType)
      setFormData(prev => ({
        ...prev,
        requested_resource_id: initialResourceId
      }))
    }
  }, [open, initialType, initialResourceId])

  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data: rolesData } = useQuery({
    queryKey: ["roles"],
    queryFn: () => rolesService.listRoles({ limit: 100 }),
    enabled: open,
  })

  const { data: resourcesData } = useQuery({
    queryKey: ["resources"],
    queryFn: () => resourcesService.listResources({ limit: 100 }),
    enabled: open,
  })

  const createMutation = useMutation({
    mutationFn: (data: AccessRequestCreatePayload) => accessRequestsService.createRequest(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["access-requests"] })
      queryClient.invalidateQueries({ queryKey: ["approval-workflows"] })
      toast({ title: "Success", description: "Access request created successfully." })
      onOpenChange(false)
      setFormData({
        business_justification: "",
        priority: "low",
      })
      setRequestType("role")
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to create access request.",
        variant: "destructive",
      })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload = { ...formData }
    if (requestType === "role") {
      delete payload.requested_resource_id
    } else {
      delete payload.requested_role_id
    }
    createMutation.mutate(payload)
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Request Access</DialogTitle>
          <DialogDescription>
            Submit a new access request for a role or resource.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-sm font-medium">Request Type</label>
            <Select
              value={requestType}
              onValueChange={(val: "role" | "resource") => setRequestType(val)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="role">Role</SelectItem>
                <SelectItem value="resource">Resource</SelectItem>
              </SelectContent>
            </Select>
          </div>
          
          {requestType === "role" && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Role</label>
              <Select
                value={formData.requested_role_id || ""}
                onValueChange={(val) => setFormData((prev) => ({ ...prev, requested_role_id: val }))}
                required
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a role" />
                </SelectTrigger>
                <SelectContent>
                  {rolesData?.items.map((role) => (
                    <SelectItem key={role.id} value={role.id}>{role.role_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {requestType === "resource" && (
            <div className="space-y-2">
              <label className="text-sm font-medium">Resource</label>
              <Select
                value={formData.requested_resource_id || ""}
                onValueChange={(val) => setFormData((prev) => ({ ...prev, requested_resource_id: val }))}
                required
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a resource" />
                </SelectTrigger>
                <SelectContent>
                  {resourcesData?.items.map((res) => (
                    <SelectItem key={res.id} value={res.id}>{res.resource_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium">Priority</label>
            <Select
              value={formData.priority}
              onValueChange={(val: any) => setFormData((prev) => ({ ...prev, priority: val }))}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select priority" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium">Business Justification</label>
            <Textarea
              name="business_justification"
              value={formData.business_justification}
              onChange={handleChange}
              placeholder="Reason for requiring this access..."
              required
              minLength={10}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending || (!formData.requested_role_id && !formData.requested_resource_id)}>
              {createMutation.isPending ? "Submitting..." : "Submit Request"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
