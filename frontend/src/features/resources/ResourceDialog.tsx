import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { resourcesService, Resource } from "@/services/resources.service"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useToast } from "@/hooks/use-toast"

interface ResourceDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  resource?: Resource | null
}

export function ResourceDialog({ open, onOpenChange, resource }: ResourceDialogProps) {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [formData, setFormData] = React.useState<Partial<Resource>>({})

  React.useEffect(() => {
    if (open) {
      if (resource) {
        setFormData(resource)
      } else {
        setFormData({
          resource_code: "",
          resource_name: "",
          resource_type: "server",
          status: "active",
          environment: "prod",
          criticality: "medium",
          connection_method: "ssh"
        })
      }
    }
  }, [open, resource])

  const mutation = useMutation({
    mutationFn: (data: Partial<Resource>) => 
      resource ? resourcesService.updateResource(resource.id, data) : resourcesService.createResource(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] })
      toast({ title: "Success", description: `Resource ${resource ? "updated" : "created"} successfully.` })
      onOpenChange(false)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to save resource.",
        variant: "destructive",
      })
    },
  })

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: name === "port" ? parseInt(value) : value }))
  }

  const handleSelectChange = (name: string, value: string) => {
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate(formData)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] overflow-y-auto max-h-[90vh]">
        <DialogHeader>
          <DialogTitle>{resource ? "Edit Resource" : "Create Resource"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Resource Code *</label>
              <Input required name="resource_code" value={formData.resource_code || ""} onChange={handleChange} disabled={!!resource} />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">Resource Name *</label>
              <Input required name="resource_name" value={formData.resource_name || ""} onChange={handleChange} />
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-medium">Type</label>
              <Select value={formData.resource_type || "server"} onValueChange={(v) => handleSelectChange("resource_type", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="application">Application</SelectItem>
                  <SelectItem value="database">Database</SelectItem>
                  <SelectItem value="server">Server</SelectItem>
                  <SelectItem value="network">Network</SelectItem>
                  <SelectItem value="cloud">Cloud</SelectItem>
                  <SelectItem value="storage">Storage</SelectItem>
                  <SelectItem value="api">API</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-medium">Environment</label>
              <Select value={formData.environment || "prod"} onValueChange={(v) => handleSelectChange("environment", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="dev">Dev</SelectItem>
                  <SelectItem value="test">Test</SelectItem>
                  <SelectItem value="staging">Staging</SelectItem>
                  <SelectItem value="prod">Prod</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Criticality</label>
              <Select value={formData.criticality || "medium"} onValueChange={(v) => handleSelectChange("criticality", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="low">Low</SelectItem>
                  <SelectItem value="medium">Medium</SelectItem>
                  <SelectItem value="high">High</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Connection Method</label>
              <Select value={formData.connection_method || "ssh"} onValueChange={(v) => handleSelectChange("connection_method", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="ssh">SSH</SelectItem>
                  <SelectItem value="rdp">RDP</SelectItem>
                  <SelectItem value="https">HTTPS</SelectItem>
                  <SelectItem value="api">API</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-medium">Hostname/IP</label>
              <Input name="hostname_ip" value={formData.hostname_ip || ""} onChange={handleChange} />
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-medium">Port</label>
              <Input type="number" name="port" value={formData.port || ""} onChange={handleChange} />
            </div>
          </div>
          
          <div className="space-y-2">
            <label className="text-sm font-medium">Description</label>
            <Textarea name="description" value={formData.description || ""} onChange={handleChange} />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={mutation.isPending}>Save</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
