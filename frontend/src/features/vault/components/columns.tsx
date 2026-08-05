import { ColumnDef } from "@tanstack/react-table"
import { VaultSecret } from "../types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { MoreHorizontal } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export const getColumns = (
  onReveal: (id: string) => void,
  onRotate: (id: string) => void,
  onDisable: (id: string) => void
): ColumnDef<VaultSecret>[] => [
  {
    accessorKey: "resource.resource_name",
    header: "Secret Name (Resource)",
    cell: ({ row }) => {
      // Fallback to ID if resource is missing (which shouldn't happen ideally)
      return row.original.resource?.resource_name || row.original.id
    },
  },
  {
    accessorKey: "resource.resource_code",
    header: "Resource Code",
    cell: ({ row }) => {
      return row.original.resource?.resource_code || "N/A"
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.getValue("status") as string
      return (
        <Badge variant={status === "active" ? "default" : "secondary"}>
          {status.toUpperCase()}
        </Badge>
      )
    },
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => {
      const date = row.getValue("created_at") as string
      if (!date) return "N/A"
      return new Date(date).toLocaleString()
    },
  },
  {
    accessorKey: "updated_at",
    header: "Updated",
    cell: ({ row }) => {
      const date = row.getValue("updated_at") as string
      if (!date) return "N/A"
      return new Date(date).toLocaleString()
    },
  },
  {
    id: "actions",
    cell: ({ row }) => {
      const secret = row.original

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
            {/* Actions will be wired up in Sprint 1.6.4 */}
            <DropdownMenuItem onClick={() => onReveal(secret.id)}>
              Reveal Secret
            </DropdownMenuItem>
            {secret.status === "active" && (
              <>
                <DropdownMenuItem onClick={() => onRotate(secret.id)}>
                  Rotate Secret
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => onDisable(secret.id)}>
                  Disable Secret
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )
    },
  },
]
