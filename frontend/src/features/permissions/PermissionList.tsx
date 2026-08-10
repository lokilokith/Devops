import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/features/authentication/AuthContext"
import { PERMISSIONS } from "@/features/authentication/authorization"
import { permissionsService, Permission } from "@/services/permissions.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, Trash, Edit, PlusCircle } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useToast } from "@/hooks/use-toast"
import { PermissionCreateModal } from "./PermissionCreateModal"
import { PermissionEditModal } from "./PermissionEditModal"

export function PermissionList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { hasPermission } = useAuth()

  // Modal state
  const [createModalOpen, setCreateModalOpen] = React.useState(false)
  const [permissionToEdit, setPermissionToEdit] = React.useState<Permission | null>(null)
  const [permissionToDelete, setPermissionToDelete] = React.useState<Permission | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["permissions", page, pageSize, search],
    queryFn: () =>
      permissionsService.listPermissions({
        skip: page * pageSize,
        limit: pageSize,
      }),
  })

  const deletePermissionMutation = useMutation({
    mutationFn: (id: string) => permissionsService.deletePermission(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["permissions"] })
      toast({ title: "Success", description: "Permission deleted successfully." })
      setPermissionToDelete(null)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to delete permission.",
        variant: "destructive",
      })
      setPermissionToDelete(null)
    },
  })

  const columns: ColumnDef<Permission>[] = [
    {
      accessorKey: "permission_code",
      header: "Code",
      cell: ({ row }) => <span className="font-mono text-sm bg-muted px-1 py-0.5 rounded">{row.getValue("permission_code")}</span>,
    },
    {
      accessorKey: "permission_name",
      header: "Name",
      cell: ({ row }) => <span className="font-medium">{row.getValue("permission_name")}</span>,
    },
    {
      accessorKey: "action",
      header: "Action",
      cell: ({ row }) => <Badge variant="outline">{row.getValue("action")}</Badge>,
    },
    {
      accessorKey: "description",
      header: "Description",
      cell: ({ row }) => (
        <span className="text-muted-foreground text-sm">
          {row.getValue("description") || "—"}
        </span>
      ),
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const status = row.getValue<string>("status")
        return (
          <Badge variant={status === "active" ? "default" : "secondary"}>
            {status || "active"}
          </Badge>
        )
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const permission = row.original
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
              {hasPermission(PERMISSIONS.PERMISSIONS_UPDATE) && (
                <DropdownMenuItem onClick={() => setPermissionToEdit(permission)}>
                  <Edit className="mr-2 h-4 w-4" />
                  Edit Permission
                </DropdownMenuItem>
              )}
              {hasPermission(PERMISSIONS.PERMISSIONS_DELETE) && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={() => setPermissionToDelete(permission)}
                    className="text-destructive"
                  >
                    <Trash className="mr-2 h-4 w-4" />
                    Delete Permission
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
      <h2 className="text-3xl font-bold tracking-tight">Permissions</h2>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search permissions..."
          onSearch={(v) => {
            setSearch(v)
            setPage(0)
          }}
        />
        {hasPermission(PERMISSIONS.PERMISSIONS_CREATE) && (
          <Button onClick={() => setCreateModalOpen(true)}>
            <PlusCircle className="mr-2 h-4 w-4" />
            Create Permission
          </Button>
        )}
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

      {/* Create Permission Modal */}
      <PermissionCreateModal open={createModalOpen} onOpenChange={setCreateModalOpen} />

      {/* Edit Permission Modal */}
      <PermissionEditModal
        permission={permissionToEdit}
        open={!!permissionToEdit}
        onOpenChange={(o) => !o && setPermissionToEdit(null)}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={!!permissionToDelete}
        onOpenChange={(o) => !o && setPermissionToDelete(null)}
        title="Delete Permission"
        description={`Are you sure you want to delete the permission "${permissionToDelete?.permission_name}"? This action cannot be undone.`}
        isDestructive
        confirmText="Delete"
        isLoading={deletePermissionMutation.isPending}
        onConfirm={() => permissionToDelete && deletePermissionMutation.mutate(permissionToDelete.id)}
      />
    </div>
  )
}
