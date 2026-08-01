import { Button } from "@/components/ui/button"
import { useAuth } from "@/features/authentication/AuthContext"
import { LogOut, User as UserIcon } from "lucide-react"

export function Header() {
  const { user, logout } = useAuth()

  return (
    <header className="flex h-14 items-center gap-4 border-b bg-background px-4 lg:h-[60px] lg:px-6">
      <div className="w-full flex-1">
        {/* Placeholder for Breadcrumbs or Search */}
      </div>
      <div className="flex items-center gap-4">
        <span className="text-sm font-medium">
          {user?.username || "Guest"}
        </span>
        <Button variant="ghost" size="icon" title="Profile">
          <UserIcon className="h-5 w-5" />
        </Button>
        <Button variant="ghost" size="icon" onClick={logout} title="Logout">
          <LogOut className="h-5 w-5" />
        </Button>
      </div>
    </header>
  )
}
