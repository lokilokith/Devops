import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { vaultService } from "../api/vault.service"
import { vaultKeys } from "../hooks/useVault"
import { resourcesService } from "@/services/resources.service"

interface CreateSecretDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function CreateSecretDialog({ open, onOpenChange }: CreateSecretDialogProps) {
  const queryClient = useQueryClient()
  const [resourceId, setResourceId] = useState("")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)

  // Fetch available resources for the dropdown
  const { data: resourcesData, isLoading: isLoadingResources } = useQuery({
    queryKey: ["resources"],
    queryFn: () => resourcesService.listResources({ limit: 1000 }),
    enabled: open, // Only fetch when dialog is open
  })

  const createMutation = useMutation({
    mutationFn: vaultService.createSecret,
    onSuccess: () => {
      // Invalidate the secrets list so it refetches
      queryClient.invalidateQueries({ queryKey: vaultKeys.secrets() })
      // Close dialog (which will also wipe state cleanly)
      handleOpenChange(false)
    },
    onError: (err: any) => {
      setError(err.response?.data?.message || err.message || "Failed to create secret")
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!resourceId || !username || !password) {
      setError("All fields are required.")
      return
    }

    const payloadObj = { username, password }
    const payload = JSON.stringify(payloadObj)

    createMutation.mutate({ resource_id: resourceId, payload })
  }

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
      // User is closing the dialog or submission successful, strictly wipe sensitive state
      setResourceId("")
      setUsername("")
      setPassword("")
      setError(null)
    }
    onOpenChange(isOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create Secret</DialogTitle>
            <DialogDescription>
              Select a resource and enter the credentials to store in the vault.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none">Resource</label>
              <Select value={resourceId} onValueChange={setResourceId} disabled={isLoadingResources}>
                <SelectTrigger>
                  <SelectValue placeholder={isLoadingResources ? "Loading..." : "Select a resource"} />
                </SelectTrigger>
                <SelectContent>
                  {resourcesData?.items.map((res) => (
                    <SelectItem key={res.id} value={res.id}>
                      {res.resource_name} ({res.resource_code})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <label htmlFor="username" className="text-sm font-medium leading-none">Username</label>
              <Input
                id="username"
                placeholder="e.g. root or admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium leading-none">Password</label>
              <Input
                id="password"
                type="password"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="off"
              />
            </div>
            {error && <div className="text-sm text-destructive">{error}</div>}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Encrypting..." : "Create Secret"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
