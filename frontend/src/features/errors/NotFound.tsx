import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { ShieldAlert } from "lucide-react"

export function NotFound() {
  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-muted/40 text-center">
      <ShieldAlert className="h-20 w-20 text-muted-foreground mb-4" />
      <h1 className="text-4xl font-bold tracking-tight mb-2">404 - Not Found</h1>
      <p className="text-muted-foreground mb-6">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <Button asChild>
        <Link to="/">Return to Dashboard</Link>
      </Button>
    </div>
  )
}
