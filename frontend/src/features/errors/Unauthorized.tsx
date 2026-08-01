import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { ShieldX } from "lucide-react"

export function Unauthorized() {
  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-muted/40 text-center">
      <ShieldX className="h-20 w-20 text-destructive mb-4" />
      <h1 className="text-4xl font-bold tracking-tight mb-2">403 - Forbidden</h1>
      <p className="text-muted-foreground mb-6">
        You do not have permission to access this resource.
      </p>
      <Button asChild>
        <Link to="/">Return to Dashboard</Link>
      </Button>
    </div>
  )
}
