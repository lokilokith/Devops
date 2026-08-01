import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { notificationsService, Notification } from "@/services/notifications.service"
import { DataTable } from "@/components/data-table/DataTable"
import { SearchBar } from "@/components/data-table/SearchBar"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MoreHorizontal, Check } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useToast } from "@/hooks/use-toast"

export function NotificationList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["notifications", page, pageSize, search],
    queryFn: () =>
      notificationsService.listNotifications({
        page: page + 1,
        per_page: pageSize,
        search,
      }),
  })

  const markReadMutation = useMutation({
    mutationFn: (id: string) => notificationsService.markRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] })
    },
  })

  const markAllReadMutation = useMutation({
    mutationFn: () => notificationsService.markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] })
      toast({ title: "Success", description: "All notifications marked as read." })
    },
  })

  const columns: ColumnDef<Notification>[] = [
    {
      accessorKey: "title",
      header: "Title",
      cell: ({ row }) => {
        const notif = row.original
        return (
          <div className="flex flex-col">
            <span className={`font-medium ${notif.is_read ? "text-muted-foreground" : "text-foreground"}`}>
              {notif.title}
            </span>
            <span className="text-sm text-muted-foreground line-clamp-1">{notif.message}</span>
          </div>
        )
      },
    },
    {
      accessorKey: "category",
      header: "Category",
      cell: ({ row }) => <Badge variant="outline">{row.getValue("category")}</Badge>,
    },
    {
      accessorKey: "created_at",
      header: "Date",
      cell: ({ row }) => new Date(row.getValue("created_at")).toLocaleString(),
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const notif = row.original
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
              {!notif.is_read && (
                <DropdownMenuItem onClick={() => markReadMutation.mutate(notif.id)}>
                  <Check className="mr-2 h-4 w-4" />
                  Mark as Read
                </DropdownMenuItem>
              )}
              {/* Add Delete action here later */}
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-3xl font-bold tracking-tight">Notification Center</h2>
        <Button variant="outline" onClick={() => markAllReadMutation.mutate()}>
          Mark All Read
        </Button>
      </div>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search notifications..."
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
        emptyMessage="You have no notifications."
        pageCount={data?.total !== undefined ? Math.max(1, Math.ceil(data.total / pageSize)) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />
    </div>
  )
}
