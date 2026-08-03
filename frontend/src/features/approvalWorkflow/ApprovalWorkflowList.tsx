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
import { Textarea } from "@/components/ui/textarea"

export function ApprovalWorkflowList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const [statusFilter] = React.useState("pending") // Hardcode to pending for now, or use a dropdown later
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [workflowToActOn, setWorkflowToActOn] = React.useState<{ wf: ApprovalWorkflow; action: "approve" | "reject" } | null>(null)
  const [comments, setComments] = React.useState("")

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["approval-workflows", page, pageSize, search, statusFilter],
    queryFn: () =>
      approvalWorkflowsService.listWorkflows({
        skip: page * pageSize,
        limit: pageSize,
        status: statusFilter === "all" ? undefined : statusFilter,
        search,
      }),
  })

  const actMutation = useMutation({
    mutationFn: ({ id, action, comments }: { id: string; action: "approve" | "reject", comments?: string }) =>
      action === "approve" ? approvalWorkflowsService.approve(id, comments) : approvalWorkflowsService.reject(id, comments),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["approval-workflows"] })
      toast({ title: "Success", description: `Request ${variables.action}d.` })
      setWorkflowToActOn(null)
      setComments("")
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Action failed.",
        variant: "destructive",
      })
    },
  })

  const columns: ColumnDef<ApprovalWorkflow>[] = [
    {
      accessorKey: "access_request_id",
      header: "Req ID",
      cell: ({ row }) => <span className="font-mono text-xs">{String(row.getValue("access_request_id")).substring(0, 8)}...</span>,
    },
    {
      accessorKey: "requested",
      header: "Requested",
      cell: ({ row }) => {
        const role = row.original.requested_role_name
        const resource = row.original.requested_resource_name
        if (role) return <Badge variant="outline">Role: {role}</Badge>
        if (resource) return <Badge variant="outline">Resource: {resource}</Badge>
        return <span className="text-muted-foreground italic">Unknown</span>
      },
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
        onOpenChange={(o) => {
          if (!o) {
            setWorkflowToActOn(null)
            setComments("")
          }
        }}
        title={workflowToActOn?.action === "approve" ? "Approve Request" : "Reject Request"}
        description={
          <div className="space-y-4 pt-4">
            <p>Are you sure you want to {workflowToActOn?.action} this request?</p>
            <div className="space-y-2">
              <label className="text-sm font-medium">Comments (Optional for Approve, Required for Reject if frontend enforces it)</label>
              <Textarea
                value={comments}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setComments(e.target.value)}
                placeholder="Enter justification..."
              />
            </div>
          </div>
        }
        isDestructive={workflowToActOn?.action === "reject"}
        confirmText={workflowToActOn?.action === "approve" ? "Approve" : "Reject"}
        isLoading={actMutation.isPending}
        onConfirm={() => workflowToActOn && actMutation.mutate({ id: workflowToActOn.wf.id, action: workflowToActOn.action, comments })}
      />
    </div>
  )
}
