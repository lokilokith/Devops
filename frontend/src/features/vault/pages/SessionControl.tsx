import { useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Loader2, RefreshCw, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react"
import { jitService, JITAccessGrant } from "../api/jit.service"
import { useToast } from "@/components/ui/use-toast"
import { Badge } from "@/components/ui/badge"

export function SessionControl() {
  const [grants, setGrants] = useState<JITAccessGrant[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const { toast } = useToast()

  const fetchSessions = async () => {
    try {
      setIsRefreshing(true)
      const data = await jitService.getCurrentSessions()
      setGrants(data)
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Error fetching sessions",
        description: "Could not retrieve your active sessions. Please try again.",
      })
    } finally {
      setIsLoading(false)
      setIsRefreshing(false)
    }
  }

  useEffect(() => {
    fetchSessions()
    // Poll every 5 seconds to get updates for pending revocations
    const interval = setInterval(() => {
      fetchSessions()
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const handleActivate = async (grantId: string) => {
    try {
      await jitService.activateGrant(grantId)
      toast({ title: "Session Activated", description: "Your privileged session is now active." })
      fetchSessions()
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Activation Failed",
        description: "Failed to activate the session.",
      })
    }
  }

  const handleTerminate = async (grantId: string) => {
    try {
      await jitService.terminateSessions(grantId)
      toast({ 
        title: "Termination Requested", 
        description: "Target revocation is running. UI will update when complete." 
      })
      fetchSessions()
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Termination Failed",
        description: "Failed to request session termination.",
      })
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return <Badge className="bg-green-500"><ShieldCheck className="mr-1 h-3 w-3" /> Active</Badge>
      case "pending":
        return <Badge variant="secondary">Pending Activation</Badge>
      case "revocation_pending":
      case "revocation_running":
        return <Badge variant="outline" className="text-orange-500 border-orange-500">
          <Loader2 className="mr-1 h-3 w-3 animate-spin" /> Revoking...
        </Badge>
      case "revoked":
      case "terminated":
        return <Badge variant="outline">Terminated</Badge>
      case "expired":
        return <Badge variant="outline" className="text-gray-500">Expired</Badge>
      case "security_uncertain":
        return <Badge variant="destructive"><ShieldAlert className="mr-1 h-3 w-3" /> Security Uncertain</Badge>
      default:
        return <Badge variant="secondary"><ShieldQuestion className="mr-1 h-3 w-3" /> {status}</Badge>
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Active Sessions</h1>
        <Button variant="outline" onClick={fetchSessions} disabled={isRefreshing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : grants.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center h-48 text-muted-foreground">
            <ShieldCheck className="h-12 w-12 mb-4 text-muted-foreground/50" />
            <p>You have no active privileged sessions.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {grants.map((grant) => (
            <Card key={grant.id} className="flex flex-col">
              <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                  <CardTitle className="text-lg">Resource Access</CardTitle>
                  {getStatusBadge(grant.status)}
                </div>
                <CardDescription className="text-xs font-mono break-all mt-1">
                  ID: {grant.id}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col space-y-4">
                <div className="text-sm space-y-2 flex-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Resource:</span>
                    <span className="font-medium truncate max-w-[140px]" title={grant.resource_id}>
                      {grant.resource_id.substring(0, 8)}...
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Expires:</span>
                    <span className="font-medium">
                      {grant.expires_at ? new Date(grant.expires_at).toLocaleTimeString() : 'N/A'}
                    </span>
                  </div>
                </div>

                <div className="flex gap-2 pt-4 mt-auto border-t">
                  {grant.status === "pending" && (
                    <Button 
                      className="flex-1" 
                      onClick={() => handleActivate(grant.id)}
                    >
                      Activate
                    </Button>
                  )}
                  
                  {['active', 'pending'].includes(grant.status) && (
                    <Button 
                      variant="destructive" 
                      className="flex-1" 
                      onClick={() => handleTerminate(grant.id)}
                    >
                      Terminate
                    </Button>
                  )}

                  {['revocation_pending', 'revocation_running'].includes(grant.status) && (
                    <Button 
                      variant="outline" 
                      className="flex-1" 
                      disabled
                    >
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Revoking
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
