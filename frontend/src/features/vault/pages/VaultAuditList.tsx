import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { auditService, AuditLog } from "@/services/audit.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Download } from "lucide-react"

export function VaultAuditList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(20)
  const [search, setSearch] = React.useState("")

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["vault-audit", page, pageSize, search],
    queryFn: () =>
      auditService.listLogs({
        page: page + 1,
        per_page: pageSize,
        search,
        resource_type: "vault_secrets",
      }),
  })

  // The page should show: User, Action, Secret, Resource, Result, Timestamp.
  const columns: ColumnDef<AuditLog>[] = [
    {
      accessorKey: "user_id",
      header: "User",
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue("user_id")}</span>,
    },
    {
      accessorKey: "action",
      header: "Action",
      cell: ({ row }) => {
        // Fallback to event_type if action is not natively exposed
        const actionStr = (row.original as any).action || row.getValue("event_type")
        return <Badge variant="outline">{actionStr}</Badge>
      },
    },
    {
      id: "secret",
      header: "Secret",
      cell: ({ row }) => {
        // resource_id usually points to the secret ID
        const secretId = (row.original as any).resource_id || "N/A"
        return <span className="font-mono text-xs">{secretId}</span>
      },
    },
    {
      id: "resource",
      header: "Resource",
      cell: ({ row }) => {
        // Vault uses details to store related Resource info, or it's attached directly
        const details = (row.original as any).details || {}
        return <span className="font-mono text-xs">{details.resource_id || "N/A"}</span>
      },
    },
    {
      id: "result",
      header: "Result",
      cell: ({ row }) => {
        // Use status or map severity to result
        const status = (row.original as any).status || "N/A"
        return (
          <Badge variant={status === "SUCCESS" ? "default" : status === "DENIED" ? "destructive" : "secondary"}>
            {status}
          </Badge>
        )
      },
    },
    {
      accessorKey: "created_at",
      header: "Timestamp",
      cell: ({ row }) => new Date(row.getValue("created_at")).toLocaleString(),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-bold tracking-tight">Vault Audit Logs</h2>
        <Button variant="outline">
          <Download className="mr-2 h-4 w-4" />
          Export CSV
        </Button>
      </div>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search vault events..."
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
        emptyMessage="No vault audit logs found."
        pageCount={data?.total ? Math.ceil(data.total / pageSize) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />
    </div>
  )
}
