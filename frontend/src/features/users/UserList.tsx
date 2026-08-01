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
import { MoreHorizontal, ShieldAlert, ShieldCheck } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { useToast } from "@/hooks/use-toast"

export function UserList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { hasPermission } = useAuth()

  const [userToToggleLock, setUserToToggleLock] = React.useState<User | null>(null)

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
      user.status === "locked" || user.status === "disabled" 
        ? usersService.unlockUser(user.id) 
        : usersService.lockUser(user.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
      toast({ title: "Success", description: "User lock status updated." })
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
      accessorKey: "roles",
      header: "Roles",
      cell: ({ row }) => {
        const roles = row.getValue<string[]>("roles") || []
        return (
          <div className="flex gap-1 flex-wrap">
            {roles.map((role) => (
              <Badge key={role} variant="outline">
                {role}
              </Badge>
            ))}
          </div>
        )
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const user = row.original
        const isLocked = user.status === "locked" || user.status === "disabled"
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
                <DropdownMenuItem onClick={() => setUserToToggleLock(user)}>
                  {!isLocked ? <ShieldAlert className="mr-2 h-4 w-4" /> : <ShieldCheck className="mr-2 h-4 w-4" />}
                  {!isLocked ? "Lock User" : "Unlock User"}
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
          <Button>Create User</Button>
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

      <ConfirmDialog
        open={!!userToToggleLock}
        onOpenChange={(o) => !o && setUserToToggleLock(null)}
        title={userToToggleLock?.status !== "locked" && userToToggleLock?.status !== "disabled" ? "Lock User" : "Unlock User"}
        description={`Are you sure you want to ${
          userToToggleLock?.status !== "locked" && userToToggleLock?.status !== "disabled" ? "lock" : "unlock"
        } ${userToToggleLock?.username}?`}
        isDestructive={userToToggleLock?.status !== "locked" && userToToggleLock?.status !== "disabled"}
        confirmText={userToToggleLock?.status !== "locked" && userToToggleLock?.status !== "disabled" ? "Lock" : "Unlock"}
        isLoading={toggleLockMutation.isPending}
        onConfirm={() => userToToggleLock && toggleLockMutation.mutate(userToToggleLock)}
      />
    </div>
  )
}
