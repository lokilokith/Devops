import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Users, ShieldCheck, Key, FolderOpen, LucideIcon } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { usersService } from "@/services/users.service"
import { rolesService } from "@/services/roles.service"
import { permissionsService } from "@/services/permissions.service"
import { resourcesService } from "@/services/resources.service"
import { Skeleton } from "@/components/ui/skeleton"

function StatCard({ 
  title, 
  icon: Icon, 
  queryKey, 
  queryFn 
}: { 
  title: string
  icon: LucideIcon
  queryKey: string[]
  queryFn: () => Promise<{ total: number }>
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn,
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-16" />
        ) : isError ? (
          <div className="text-sm text-destructive font-bold">Error</div>
        ) : (
          <div className="text-2xl font-bold">{data?.total ?? 0}</div>
        )}
      </CardContent>
    </Card>
  )
}

export function Dashboard() {
  return (
    <div className="space-y-4">
      <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
      
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard 
          title="Total Users" 
          icon={Users} 
          queryKey={["dashboard-users"]} 
          queryFn={() => usersService.listUsers({ limit: 1 })} 
        />
        <StatCard 
          title="Roles Defined" 
          icon={ShieldCheck} 
          queryKey={["dashboard-roles"]} 
          queryFn={() => rolesService.listRoles({ limit: 1 })} 
        />
        <StatCard 
          title="Permissions" 
          icon={Key} 
          queryKey={["dashboard-permissions"]} 
          queryFn={() => permissionsService.listPermissions({ limit: 1 })} 
        />
        <StatCard 
          title="Resources" 
          icon={FolderOpen} 
          queryKey={["dashboard-resources"]} 
          queryFn={() => resourcesService.listResources({ limit: 1 })} 
        />
      </div>
      
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card className="col-span-4">
          <CardHeader>
            <CardTitle>Recent Security Events</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground">
              Feature coming soon...
            </div>
          </CardContent>
        </Card>
        <Card className="col-span-3">
          <CardHeader>
            <CardTitle>Pending Approvals</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground">
              No pending approvals.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
