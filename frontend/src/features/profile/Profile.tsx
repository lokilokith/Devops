import { useAuth } from "@/features/authentication/AuthContext"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { User as UserIcon } from "lucide-react"

export function Profile() {
  const { user } = useAuth()

  return (
    <div className="space-y-4 max-w-4xl">
      <h2 className="text-3xl font-bold tracking-tight">My Profile</h2>
      
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-1">
          <CardHeader className="text-center">
            <div className="flex justify-center mb-4">
              <div className="h-24 w-24 bg-muted rounded-full flex items-center justify-center">
                <UserIcon className="h-12 w-12 text-muted-foreground" />
              </div>
            </div>
            <CardTitle>{user?.username || "Guest"}</CardTitle>
            <CardDescription>User ID: {user?.id || "N/A"}</CardDescription>
            <Button className="w-full mt-4" variant="outline">Upload Avatar</Button>
          </CardHeader>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Personal Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none">Username</label>
              <Input defaultValue={user?.username} disabled />
            </div>
            
            <div className="space-y-2">
              <label className="text-sm font-medium leading-none">Roles</label>
              <div className="flex gap-2 flex-wrap mt-1">
                {user?.roles.map((role) => (
                  <Badge key={role} variant="default">{role}</Badge>
                ))}
              </div>
            </div>

          </CardContent>
        </Card>

        <Card className="md:col-span-3">
          <CardHeader>
            <CardTitle>Security</CardTitle>
            <CardDescription>Update your password and security settings here.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2 max-w-sm">
              <label className="text-sm font-medium leading-none">Current Password</label>
              <Input type="password" />
            </div>
            <div className="space-y-2 max-w-sm">
              <label className="text-sm font-medium leading-none">New Password</label>
              <Input type="password" />
            </div>
            <div className="space-y-2 max-w-sm">
              <label className="text-sm font-medium leading-none">Confirm New Password</label>
              <Input type="password" />
            </div>
            <Button>Update Password</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
