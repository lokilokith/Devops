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
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { vaultService } from "../api/vault.service"
import { vaultKeys } from "../hooks/useVault"
import { useToast } from "@/hooks/use-toast"

interface RotateSecretDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  secretId: string | null
}

export function RotateSecretDialog({ open, onOpenChange, secretId }: RotateSecretDialogProps) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)

  const rotateMutation = useMutation({
    mutationFn: (payload: { payload: string }) => vaultService.rotateSecret(secretId!, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: vaultKeys.secrets() })
      toast({ title: "Secret Rotated", description: "The secret has been successfully rotated." })
      handleOpenChange(false)
    },
    onError: (err: any) => {
      setError(err.response?.data?.message || err.message || "Failed to rotate secret")
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!password) {
      setError("Password is required.")
      return
    }

    rotateMutation.mutate({ payload: password })
  }

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) {
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
            <DialogTitle>Rotate Secret</DialogTitle>
            <DialogDescription>
              Enter a new password. The old version will be archived and replaced with this new one.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label htmlFor="password-rotate" className="text-sm font-medium leading-none">New Password</label>
              <Input
                id="password-rotate"
                type="password"
                placeholder="Enter new password"
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
              disabled={rotateMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={rotateMutation.isPending}>
              {rotateMutation.isPending ? "Rotating..." : "Rotate Secret"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
