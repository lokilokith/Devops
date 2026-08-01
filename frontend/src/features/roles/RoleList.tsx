import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { rolesService, Role } from "@/services/roles.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, Trash } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useToast } from "@/hooks/use-toast"

export function RoleList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [roleToDelete, setRoleToDelete] = React.useState<Role | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["roles", page, pageSize, search],
    queryFn: () =>
      rolesService.listRoles({
        skip: page * pageSize,
        limit: pageSize,
        search,
      }),
  })

  const deleteRoleMutation = useMutation({
    mutationFn: (id: string) => rolesService.deleteRole(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["roles"] })
      toast({ title: "Success", description: "Role deleted successfully." })
      setRoleToDelete(null)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to delete role.",
        variant: "destructive",
      })
      setRoleToDelete(null)
    },
  })

  const columns: ColumnDef<Role>[] = [
    {
      accessorKey: "role_name",
      header: "Name",
      cell: ({ row }) => <span className="font-medium">{row.getValue("role_name")}</span>,
    },
    {
      accessorKey: "description",
      header: "Description",
    },
    {
      accessorKey: "permissions",
      header: "Permissions Count",
      cell: ({ row }) => {
        const perms = row.getValue<string[]>("permissions") || []
        return <Badge variant="secondary">{perms.length} Permissions</Badge>
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const role = row.original
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
              <DropdownMenuItem onClick={() => setRoleToDelete(role)} className="text-destructive">
                <Trash className="mr-2 h-4 w-4" />
                Delete Role
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-3xl font-bold tracking-tight">Roles</h2>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search roles..."
          onSearch={(v) => {
            setSearch(v)
            setPage(1)
          }}
        />
        <Button>Create Role</Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => refetch()}
        emptyMessage="No roles found."
        pageCount={data?.total ? Math.ceil(data.total / pageSize) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />

      <ConfirmDialog
        open={!!roleToDelete}
        onOpenChange={(o) => !o && setRoleToDelete(null)}
        title="Delete Role"
        description={`Are you sure you want to delete the role "${roleToDelete?.role_name}"? This action cannot be undone.`}
        isDestructive
        confirmText="Delete"
        isLoading={deleteRoleMutation.isPending}
        onConfirm={() => roleToDelete && deleteRoleMutation.mutate(roleToDelete.id)}
      />
    </div>
  )
}
