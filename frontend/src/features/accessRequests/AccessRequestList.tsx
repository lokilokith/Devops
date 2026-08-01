import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { accessRequestsService, AccessRequest } from "@/services/access-requests.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, XCircle } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useToast } from "@/hooks/use-toast"

export function AccessRequestList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [requestToCancel, setRequestToCancel] = React.useState<AccessRequest | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["access-requests", page, pageSize, search],
    queryFn: () =>
      accessRequestsService.listRequests({
        skip: page * pageSize,
        limit: pageSize,
        search,
      }),
  })

  const cancelRequestMutation = useMutation({
    mutationFn: (id: string) => accessRequestsService.cancelRequest(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["access-requests"] })
      toast({ title: "Success", description: "Request cancelled." })
      setRequestToCancel(null)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to cancel request.",
        variant: "destructive",
      })
      setRequestToCancel(null)
    },
  })

  const columns: ColumnDef<AccessRequest>[] = [
    {
      accessorKey: "resource_name",
      header: "Resource",
      cell: ({ row }) => <span className="font-medium">{row.getValue("resource_name")}</span>,
    },
    {
      accessorKey: "permission_name",
      header: "Permission",
      cell: ({ row }) => <Badge variant="outline">{row.getValue("permission_name")}</Badge>,
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const status = row.getValue<string>("status")
        const variantMap: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
          pending: "secondary",
          approved: "default",
          rejected: "destructive",
          cancelled: "outline",
          expired: "outline",
        }
        return <Badge variant={variantMap[status] || "default"}>{status.toUpperCase()}</Badge>
      },
    },
    {
      accessorKey: "created_at",
      header: "Requested On",
      cell: ({ row }) => new Date(row.getValue("created_at")).toLocaleDateString(),
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const req = row.original
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
              {req.status === "pending" && (
                <DropdownMenuItem onClick={() => setRequestToCancel(req)} className="text-destructive">
                  <XCircle className="mr-2 h-4 w-4" />
                  Cancel Request
                </DropdownMenuItem>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-3xl font-bold tracking-tight">My Access Requests</h2>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search requests..."
          onSearch={(v) => {
            setSearch(v)
            setPage(0)
          }}
        />
        <Button>Request Access</Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => refetch()}
        emptyMessage="No access requests found."
        pageCount={data?.total !== undefined ? Math.max(1, Math.ceil(data.total / pageSize)) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />

      <ConfirmDialog
        open={!!requestToCancel}
        onOpenChange={(o) => !o && setRequestToCancel(null)}
        title="Cancel Request"
        description="Are you sure you want to cancel this pending access request?"
        isDestructive
        confirmText="Cancel Request"
        isLoading={cancelRequestMutation.isPending}
        onConfirm={() => requestToCancel && cancelRequestMutation.mutate(requestToCancel.id)}
      />
    </div>
  )
}
