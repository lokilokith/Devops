import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useAuth } from "@/features/authentication/AuthContext"
import { PERMISSIONS } from "@/features/authentication/authorization"
import { usersService, User } from "@/services/users.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, ShieldAlert, ShieldCheck, Edit, Trash2 } from "lucide-react"
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
import { UserCreateModal } from "./UserCreateModal"
import { UserEditModal } from "./UserEditModal"

export function UserList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { hasPermission } = useAuth()

  const [createModalOpen, setCreateModalOpen] = React.useState(false)
  const [userToEdit, setUserToEdit] = React.useState<User | null>(null)
  const [userToToggleLock, setUserToToggleLock] = React.useState<User | null>(null)
  const [userToDelete, setUserToDelete] = React.useState<User | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["users", page, pageSize, search],
    queryFn: () =>
      usersService.listUsers({
        skip: page * pageSize,
        limit: pageSize,
        search,
      }),
  })

  const toggleLockMutation = useMutation({
    mutationFn: (user: User) => 
      user.status === "disabled" || user.status === "locked"
        ? usersService.enableUser(user.id) 
        : usersService.disableUser(user.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      toast({ title: "Success", description: "User status updated." })
      setUserToToggleLock(null)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to update user.",
        variant: "destructive",
      })
      setUserToToggleLock(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => usersService.deleteUser(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      toast({ title: "Success", description: "User deleted successfully." })
      setUserToDelete(null)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to delete user.",
        variant: "destructive",
      })
      setUserToDelete(null)
    },
  })

  const columns: ColumnDef<User>[] = [
    {
      accessorKey: "username",
      header: "Username",
    },
    {
      accessorKey: "email",
      header: "Email",
    },
    {
      accessorKey: "full_name",
      header: "Full Name",
    },
    {
      accessorKey: "employee_id",
      header: "Employee ID",
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const status = row.getValue("status")
        return (
          <Badge variant={status === "active" ? "default" : "destructive"}>
            {status === "active" ? "Active" : String(status)}
          </Badge>
        )
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const user = row.original
        const isDisabled = user.status === "disabled" || user.status === "locked"
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
              {hasPermission(PERMISSIONS.USERS_UPDATE) && (
                <DropdownMenuItem onClick={() => setUserToEdit(user)}>
                  <Edit className="mr-2 h-4 w-4" /> Edit User
                </DropdownMenuItem>
              )}
              {hasPermission(PERMISSIONS.USERS_UPDATE) && (
                <DropdownMenuItem onClick={() => setUserToToggleLock(user)}>
                  {!isDisabled ? <ShieldAlert className="mr-2 h-4 w-4" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
                  {!isDisabled ? "Disable User" : "Enable User"}
                </DropdownMenuItem>
              )}
              {hasPermission(PERMISSIONS.USERS_DELETE) && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => setUserToDelete(user)} className="text-destructive">
                    <Trash2 className="mr-2 h-4 w-4" /> Delete User
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
      <h2 className="text-3xl font-bold tracking-tight">Users</h2>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search users..."
          onSearch={(v) => {
            setSearch(v)
            setPage(0)
          }}
        />
        {hasPermission(PERMISSIONS.USERS_CREATE) && (
          <Button onClick={() => setCreateModalOpen(true)}>Create User</Button>
        )}
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => refetch()}
        emptyMessage="No users found."
        pageCount={data?.total ? Math.ceil(data.total / pageSize) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />

      <UserCreateModal open={createModalOpen} onOpenChange={setCreateModalOpen} />
      <UserEditModal user={userToEdit} open={!!userToEdit} onOpenChange={(o) => !o && setUserToEdit(null)} />

      <ConfirmDialog
        open={!!userToToggleLock}
        onOpenChange={(o) => !o && setUserToToggleLock(null)}
        title={userToToggleLock?.status !== "disabled" && userToToggleLock?.status !== "locked" ? "Disable User" : "Enable User"}
        description={`Are you sure you want to ${
          userToToggleLock?.status !== "disabled" && userToToggleLock?.status !== "locked" ? "disable" : "enable"
        } ${userToToggleLock?.username}?`}
        isDestructive={userToToggleLock?.status !== "disabled" && userToToggleLock?.status !== "locked"}
        confirmText={userToToggleLock?.status !== "disabled" && userToToggleLock?.status !== "locked" ? "Disable" : "Enable"}
        isLoading={toggleLockMutation.isPending}
        onConfirm={() => userToToggleLock && toggleLockMutation.mutate(userToToggleLock)}
      />

      <ConfirmDialog
        open={!!userToDelete}
        onOpenChange={(o) => !o && setUserToDelete(null)}
        title="Delete User"
        description={`Are you sure you want to permanently delete ${userToDelete?.username}?`}
        isDestructive={true}
        confirmText="Delete"
        isLoading={deleteMutation.isPending}
        onConfirm={() => userToDelete && deleteMutation.mutate(userToDelete.id)}
      />
    </div>
  )
}
