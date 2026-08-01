import { NavLink } from "react-router-dom"
import {
  LayoutDashboard,
  Users,
  ShieldCheck,
  Key,
  FolderOpen,
  ClipboardList,
  CheckSquare,
  Bell,
  ScrollText,
} from "lucide-react"
import { useAuth } from "@/features/authentication/AuthContext"
import { PERMISSIONS } from "@/features/authentication/authorization"

export function Sidebar() {
  const { hasPermission } = useAuth()

  const navItems = [
    { name: "Dashboard", to: "/dashboard", icon: LayoutDashboard },
    ...(hasPermission(PERMISSIONS.USERS_READ) ? [{ name: "Users", to: "/users", icon: Users }] : []),
    ...(hasPermission(PERMISSIONS.ROLES_READ) ? [{ name: "Roles", to: "/roles", icon: ShieldCheck }] : []),
    ...(hasPermission(PERMISSIONS.PERMISSIONS_READ) ? [{ name: "Permissions", to: "/permissions", icon: Key }] : []),
    ...(hasPermission(PERMISSIONS.RESOURCES_READ) ? [{ name: "Resources", to: "/resources", icon: FolderOpen }] : []),
    { name: "Access Requests", to: "/access-requests", icon: ClipboardList },
    { name: "Approvals", to: "/approvals", icon: CheckSquare },
    { name: "Notifications", to: "/notifications", icon: Bell },
    ...(hasPermission(PERMISSIONS.AUDIT_READ) ? [{ name: "Audit Logs", to: "/audit", icon: ScrollText }] : []),
  ]

  return (
    <aside className="fixed inset-y-0 left-0 z-10 hidden w-64 flex-col border-r bg-background sm:flex">
      <div className="flex h-14 items-center border-b px-4 lg:h-[60px] lg:px-6">
        <NavLink to="/" className="flex items-center gap-2 font-semibold">
          <ShieldCheck className="h-6 w-6" />
          <span className="">OpsForge PAM</span>
        </NavLink>
      </div>
      <div className="flex-1 overflow-auto py-2">
        <nav className="grid items-start px-2 text-sm font-medium lg:px-4">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 transition-all hover:text-primary ${isActive ? "bg-muted text-primary" : "text-muted-foreground"
                }`
              }
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </NavLink>
          ))}
        </nav>
      </div>
    </aside>
  )
}
