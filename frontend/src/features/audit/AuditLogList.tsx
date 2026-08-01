import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { auditService, AuditLog } from "@/services/audit.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Download } from "lucide-react"

export function AuditLogList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(20)
  const [search, setSearch] = React.useState("")

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["audit", page, pageSize, search],
    queryFn: () =>
      auditService.listLogs({
        page: page + 1,
        per_page: pageSize,
        search,
      }),
  })

  const columns: ColumnDef<AuditLog>[] = [
    {
      accessorKey: "event_type",
      header: "Event",
      cell: ({ row }) => <Badge variant="outline">{row.getValue("event_type")}</Badge>,
    },
    {
      accessorKey: "user_id",
      header: "User ID",
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue("user_id")}</span>,
    },
    {
      accessorKey: "ip_address",
      header: "IP Address",
      cell: ({ row }) => <span className="font-mono text-xs">{row.getValue("ip_address")}</span>,
    },
    {
      accessorKey: "details",
      header: "Details",
      cell: ({ row }) => <span className="text-sm truncate max-w-[200px] block">{row.getValue("details")}</span>,
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
        <h2 className="text-3xl font-bold tracking-tight">Audit Logs</h2>
        <Button variant="outline">
          <Download className="mr-2 h-4 w-4" />
          Export CSV
        </Button>
      </div>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search logs..."
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
        emptyMessage="No audit logs found."
        pageCount={data?.total ? Math.ceil(data.total / pageSize) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />
    </div>
  )
}
