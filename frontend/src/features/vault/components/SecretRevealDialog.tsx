import { useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Copy, Check } from "lucide-react"

interface SecretRevealDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  secretValue: string | null
}

export function SecretRevealDialog({ open, onOpenChange, secretValue }: SecretRevealDialogProps) {
  const [timeLeft, setTimeLeft] = useState(30)
  const [copied, setCopied] = useState(false)

  // Clear state when dialog opens or closes, start timer when opened
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>
    if (open) {
      setTimeLeft(30)
      setCopied(false)
      timer = setInterval(() => {
        setTimeLeft((prev) => {
          if (prev <= 1) {
            clearInterval(timer)
            onOpenChange(false) // auto close
            return 0
          }
          return prev - 1
        })
      }, 1000)
    }
    return () => {
      if (timer) clearInterval(timer)
    }
  }, [open, onOpenChange])

  const handleCopy = () => {
    if (secretValue) {
      navigator.clipboard.writeText(secretValue)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  // Ensure secret is strictly wiped from memory when closed via unmount pattern upstream.
  // The value is nullified externally, but we also don't render it if not open.

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Secret Payload</DialogTitle>
          <DialogDescription>
            This secret is temporarily revealed. It will automatically hide in{" "}
            <strong className="text-foreground">{timeLeft}</strong> seconds.
          </DialogDescription>
        </DialogHeader>
        <div className="flex items-center space-x-2 mt-4">
          <div className="grid flex-1 gap-2">
            <div className="rounded-md border bg-muted p-4 font-mono text-sm break-all">
              {secretValue ? secretValue : "Wiped."}
            </div>
          </div>
          <Button type="button" size="sm" className="px-3" onClick={handleCopy}>
            <span className="sr-only">Copy</span>
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
