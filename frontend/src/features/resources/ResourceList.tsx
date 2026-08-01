import * as React from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { resourcesService, Resource } from "@/services/resources.service"
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

export function ResourceList() {
  const [page, setPage] = React.useState(0)
  const [pageSize, setPageSize] = React.useState(10)
  const [search, setSearch] = React.useState("")
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const [resourceToDelete, setResourceToDelete] = React.useState<Resource | null>(null)

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["resources", page, pageSize, search],
    queryFn: () =>
      resourcesService.listResources({
        skip: page * pageSize,
        limit: pageSize,
        search,
      }),
  })

  const deleteResourceMutation = useMutation({
    mutationFn: (id: string) => resourcesService.deleteResource(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resources"] })
      toast({ title: "Success", description: "Resource deleted successfully." })
      setResourceToDelete(null)
    },
    onError: (error: any) => {
      toast({
        title: "Error",
        description: error.response?.data?.message || "Failed to delete resource.",
        variant: "destructive",
      })
      setResourceToDelete(null)
    },
  })

  const columns: ColumnDef<Resource>[] = [
    {
      accessorKey: "resource_name",
      header: "Name",
      cell: ({ row }) => <span className="font-medium">{row.getValue("resource_name")}</span>,
    },
    {
      accessorKey: "description",
      header: "Description",
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const status = row.getValue<string>("status")
        return (
          <Badge variant={status === "active" ? "default" : "secondary"}>
            {status}
          </Badge>
        )
      },
    },
    {
      id: "actions",
      cell: ({ row }) => {
        const resource = row.original
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
              <DropdownMenuItem onClick={() => setResourceToDelete(resource)} className="text-destructive">
                <Trash className="mr-2 h-4 w-4" />
                Delete Resource
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-3xl font-bold tracking-tight">Resources</h2>
      
      <div className="flex justify-between items-center">
        <SearchBar
          placeholder="Search resources..."
          onSearch={(v) => {
            setSearch(v)
            setPage(0)
          }}
        />
        <Button>Create Resource</Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        isError={isError}
        onRetry={() => refetch()}
        emptyMessage="No resources found."
        pageCount={data?.total ? Math.ceil(data.total / pageSize) : -1}
        onPaginationChange={(idx, size) => {
          setPage(idx)
          setPageSize(size)
        }}
      />

      <ConfirmDialog
        open={!!resourceToDelete}
        onOpenChange={(o) => !o && setResourceToDelete(null)}
        title="Delete Resource"
        description={`Are you sure you want to delete the resource ${resourceToDelete?.resource_name}?`}
        isDestructive
        confirmText="Delete"
        isLoading={deleteResourceMutation.isPending}
        onConfirm={() => resourceToDelete && deleteResourceMutation.mutate(resourceToDelete.id)}
      />
    </div>
  )
}
