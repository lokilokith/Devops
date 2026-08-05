import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useState, useMemo } from "react"
import { DataTable } from "@/components/data-table/DataTable"
import { getColumns } from "../components/columns"
import { useVaultSecrets, vaultKeys } from "../hooks/useVault"
import { Button } from "@/components/ui/button"
import { Plus } from "lucide-react"
import { CreateSecretDialog } from "../components/CreateSecretDialog"
import { SecretRevealDialog } from "../components/SecretRevealDialog"
import { AccessRequestCreateModal } from "@/features/accessRequests/AccessRequestCreateModal"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { vaultService } from "../api/vault.service"
import { useToast } from "@/hooks/use-toast"

export function SecretList() {
  const { data: secrets, isLoading, isError, refetch } = useVaultSecrets()
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [createOpen, setCreateOpen] = useState(false)
  const [revealOpen, setRevealOpen] = useState(false)
  const [revealedValue, setRevealedValue] = useState<string | null>(null)
  
  const [disableOpen, setDisableOpen] = useState(false)
  const [selectedSecretId, setSelectedSecretId] = useState<string | null>(null)

  const [accessRequestOpen, setAccessRequestOpen] = useState(false)
  const [accessRequestResourceId, setAccessRequestResourceId] = useState<string | undefined>()

  const retrieveMutation = useMutation({
    mutationFn: vaultService.retrieveSecret,
    onSuccess: (data) => {
      setRevealedValue(data.payload)
      setRevealOpen(true)
    },
    onError: (error: any) => {
      // Handle the specific Vault APPROVAL_REQUIRED flow
      if (error.response?.data?.error === "APPROVAL_REQUIRED" && error.response?.data?.resource_id) {
        setAccessRequestResourceId(error.response.data.resource_id)
        setAccessRequestOpen(true)
        toast({
          title: "Approval Required",
          description: "You must request access before viewing this secret.",
        })
        return
      }

      toast({
        title: "Access Denied",
        description: error.message || "Failed to retrieve secret",
        variant: "destructive",
      })
    },
  })

  const disableMutation = useMutation({
    mutationFn: vaultService.disableSecret,
    onSuccess: () => {
      toast({ title: "Secret Disabled", description: "The secret has been disabled." })
      queryClient.invalidateQueries({ queryKey: vaultKeys.secrets() })
      setDisableOpen(false)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.message || "Failed to disable secret",
        variant: "destructive",
      })
    },
  })

  const handleReveal = (id: string) => {
    retrieveMutation.mutate(id)
  }

  const handleDisable = (id: string) => {
    setSelectedSecretId(id)
    setDisableOpen(true)
  }

  const handleConfirmDisable = () => {
    if (selectedSecretId) {
      disableMutation.mutate(selectedSecretId)
    }
  }

  const handleRevealClose = (open: boolean) => {
    if (!open) {
      setRevealedValue(null) // wipe locally immediately
    }
    setRevealOpen(open)
  }

  const tableColumns = useMemo(() => getColumns(handleReveal, handleDisable), [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Secrets</h1>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" /> Add Secret
        </Button>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Vault Secrets</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={tableColumns}
            data={secrets || []}
            searchKey="resource.resource_name"
            isLoading={isLoading}
            isError={isError}
            onRetry={refetch}
            emptyMessage="No secrets found."
          />
        </CardContent>
      </Card>
      <CreateSecretDialog open={createOpen} onOpenChange={setCreateOpen} />
      <SecretRevealDialog open={revealOpen} onOpenChange={handleRevealClose} secretValue={revealedValue} />
      
      <AccessRequestCreateModal 
        open={accessRequestOpen} 
        onOpenChange={setAccessRequestOpen} 
        initialType="resource"
        initialResourceId={accessRequestResourceId}
      />

      <ConfirmDialog 
        open={disableOpen} 
        onOpenChange={setDisableOpen} 
        title="Disable Secret" 
        description="Are you sure you want to disable this secret? It will no longer be accessible for active use." 
        confirmText="Disable" 
        onConfirm={handleConfirmDisable} 
        isDestructive={true}
        isLoading={disableMutation.isPending}
      />
    </div>
  )
}
