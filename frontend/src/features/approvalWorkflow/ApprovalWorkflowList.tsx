import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { approvalWorkflowsService, ApprovalWorkflow } from "@/services/approval-workflows.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, CheckCircle, XCircle } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useToast } from "@/hooks/use-toast"

export function ApprovalWorkflowList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [workflowToActOn, setWorkflowToActOn] = React.useState<{ wf: ApprovalWorkflow; action: "approve" | "reject" } | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["approval-workflows", page, pageSize, search],
    queryFn: () =>
      approvalWorkflowsService.listWorkflows({
        skip: page * pageSize,
        limit: pageSize,
        status: undefined,
      }),
  })

  const actMutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "approve" | "reject" }) =>
      action === "approve" ? approvalWorkflowsService.approve(id) : approvalWorkflowsService.reject(id),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["approval-workflows"] })
      toast({ title: "Success", description: `Request ${variables.action}d.` })
      setWorkflowToActOn(null)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Action failed.",
        variant: "destructive",
      })
      setWorkflowToActOn(null)
    },
  })

  const columns: ColumnDef<ApprovalWorkflow>[] = [
    {
      accessorKey: "id",
      header: "Workflow ID",
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue("id")}</span>,
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const status = row.getValue<string>("status")
        const variantMap: Record<string, "default" | "secondary" | "destructive"> = {
          pending: "secondary",
          approved: "default",
          rejected: "destructive",
        }
        return <Badge variant={variantMap[status]}>{status.toUpperCase()}</Badge>
      },
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ row }) => new Date(row.getValue("created_at")).toLocaleString(),
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const wf = row.original
        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Actions</DropdownMenuLabel>
              {wf.status === "pending" && (
                <>
                  <DropdownMenuItem onClick={() => setWorkflowToActOn({ wf, action: "approve" })}>
                    <CheckCircle className="mr-2 h-4 w-4 text-green-500" />
                    Approve
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={() => setWorkflowToActOn({ wf, action: "reject" })} className="text-destructive">
                    <XCircle className="mr-2 h-4 w-4" />
                    Reject
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-3xl font-bold tracking-tight">Approval Queue</h2>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search approvals..."
          onSearch={(v) => {
            setSearch(v)
            setPage(0)
          }}
        />
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => refetch()}
        emptyMessage="No pending approvals found."
        pageCount={data?.total !== undefined ? Math.max(1, Math.ceil(data.total / pageSize)) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />

      <ConfirmDialog
        open={!!workflowToActOn}
        onOpenChange={(o) => !o && setWorkflowToActOn(null)}
        title={workflowToActOn?.action === "approve" ? "Approve Request" : "Reject Request"}
        description={`Are you sure you want to ${workflowToActOn?.action} this request?`}
        isDestructive={workflowToActOn?.action === "reject"}
        confirmText={workflowToActOn?.action === "approve" ? "Approve" : "Reject"}
        isLoading={actMutation.isPending}
        onConfirm={() => workflowToActOn && actMutation.mutate({ id: workflowToActOn.wf.id, action: workflowToActOn.action })}
      />
    </div>
  )
}
