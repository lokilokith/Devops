import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { permissionsService, Permission } from "@/services/permissions.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"

export function PermissionList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["permissions", page, pageSize, search],
    queryFn: () =>
      permissionsService.listPermissions({
        skip: page * pageSize,
        limit: pageSize,
      }),
  })

  const columns: ColumnDef<Permission>[] = [
    {
      accessorKey: "name",
      header: "Permission Name",
      cell: ({ row }) => <span className="font-mono">{row.getValue("name")}</span>,
    },
    {
      accessorKey: "description",
      header: "Description",
    },
    {
      accessorKey: "resource",
      header: "Resource Group",
      cell: ({ row }) => {
        const resource = row.getValue<string>("resource")
        return <Badge variant="outline">{resource}</Badge>
      },
    },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-3xl font-bold tracking-tight">Permissions</h2>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search permissions..."
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
        emptyMessage="No permissions found."
        pageCount={data?.total ? Math.ceil(data.total / pageSize) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />
    </div>
  )
}
