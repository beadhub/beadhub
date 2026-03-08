import { useState, useEffect, useRef } from "react"
import { useMutation } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import { Send, Loader2 } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog"
import { Button } from "./ui/button"
import { Input } from "./ui/input"
import { Textarea } from "./ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select"
import { type ApiClient } from "../lib/api"
import { useStore } from "../hooks/useStore"

const MAX_SUBJECT_LENGTH = 200
const MAX_BODY_LENGTH = 10000
const SEND_RETRY_DELAYS_MS = [250, 500] as const

function sleep(ms: number) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

function isRetryableSendError(error: unknown) {
  if (typeof error === "object" && error !== null && "status" in error) {
    const status = (error as { status?: unknown }).status
    return typeof status === "number" && status >= 500 && status < 600
  }

  return error instanceof TypeError
}

async function sendMessageWithRetry<T>(send: () => Promise<T>) {
  for (let attempt = 0; attempt <= SEND_RETRY_DELAYS_MS.length; attempt += 1) {
    try {
      return await send()
    } catch (error) {
      const shouldRetry =
        attempt < SEND_RETRY_DELAYS_MS.length && isRetryableSendError(error)
      if (!shouldRetry) {
        throw error
      }
      await sleep(SEND_RETRY_DELAYS_MS[attempt])
    }
  }

  throw new Error("Message send failed after retries")
}

interface SendMessageDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  targetWorkspaceId?: string
  targetAlias?: string
}

export function SendMessageDialog({
  open,
  onOpenChange,
  targetWorkspaceId,
  targetAlias,
}: SendMessageDialogProps) {
  const api = useApi<ApiClient>()
  const { dashboardIdentity, identityLoading, identityError } = useStore()
  const [subject, setSubject] = useState("")
  const [body, setBody] = useState("")
  const [priority, setPriority] = useState<"low" | "normal" | "high">("normal")
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const sendMutation = useMutation({
    mutationFn: async () => {
      if (!dashboardIdentity) {
        throw new Error("Dashboard identity not initialized")
      }
      if (!targetWorkspaceId) {
        throw new Error("No target workspace specified")
      }
      if (subject.length > MAX_SUBJECT_LENGTH) {
        throw new Error(`Subject exceeds ${MAX_SUBJECT_LENGTH} characters`)
      }
      if (body.length > MAX_BODY_LENGTH) {
        throw new Error(`Message exceeds ${MAX_BODY_LENGTH} characters`)
      }
      if (!body.trim()) {
        throw new Error("Message cannot be empty")
      }
      return sendMessageWithRetry(() =>
        api.sendMessage(
          dashboardIdentity.workspace_id,
          dashboardIdentity.alias,
          targetWorkspaceId,
          subject,
          body,
          priority
        )
      )
    },
    onMutate: () => {
      setError(null)
      setSuccess(false)
    },
    onSuccess: () => {
      setSuccess(true)
      setError(null)
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
      successTimeoutRef.current = setTimeout(() => {
        resetForm()
        onOpenChange(false)
      }, 2500)
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      setSuccess(false)
    },
  })

  const resetForm = () => {
    setSubject("")
    setBody("")
    setPriority("normal")
    setError(null)
    setSuccess(false)
  }

  // Reset form when target workspace changes while dialog is open
  const prevTargetRef = useRef(targetWorkspaceId)
  useEffect(() => {
    if (open && prevTargetRef.current !== targetWorkspaceId && !sendMutation.isPending) {
      // Clear any pending success timeout
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
        successTimeoutRef.current = null
      }
      // Reset form state inline to avoid dependency issues
      setSubject("")
      setBody("")
      setPriority("normal")
      setError(null)
      setSuccess(false)
    }
    prevTargetRef.current = targetWorkspaceId
  }, [targetWorkspaceId, open, sendMutation.isPending])

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current)
      }
    }
  }, [])

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen && sendMutation.isPending) {
      return
    }
    if (!newOpen) {
      resetForm()
    }
    onOpenChange(newOpen)
  }

  const canSend = dashboardIdentity && targetWorkspaceId && body.trim() && !identityLoading && !identityError
  const formDisabled = sendMutation.isPending || identityLoading || !!identityError

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault()
      if (canSend && !sendMutation.isPending && !success) {
        sendMutation.mutate()
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="h-4 w-4" />
            Send Message
          </DialogTitle>
          <DialogDescription>
            Send a message to {targetAlias || "workspace"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Identity loading state */}
          {identityLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted p-3 rounded">
              <Loader2 className="h-4 w-4 animate-spin" />
              Initializing messaging identity...
            </div>
          )}

          {/* Identity error state */}
          {identityError && !identityLoading && (
            <div className="text-sm text-destructive bg-destructive/10 p-3 rounded">
              {identityError}
            </div>
          )}

          {/* Target (read-only) */}
          <div className="space-y-2">
            <label className="text-sm font-medium">To</label>
            <Input
              value={targetAlias || targetWorkspaceId || ""}
              disabled
              className="bg-muted"
            />
          </div>

          {/* Subject */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Subject</label>
            <Input
              placeholder="Optional subject line"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              disabled={formDisabled}
              maxLength={MAX_SUBJECT_LENGTH}
            />
          </div>

          {/* Body */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium">Message</label>
              <div className="flex items-center gap-3 text-xs text-muted-foreground">
                <span className="hidden sm:inline">Ctrl+Enter to send</span>
                <span>{body.length}/{MAX_BODY_LENGTH}</span>
              </div>
            </div>
            <Textarea
              placeholder="Enter your message..."
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={formDisabled}
              rows={4}
              maxLength={MAX_BODY_LENGTH}
            />
          </div>

          {/* Priority */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Priority</label>
            <Select
              value={priority}
              onValueChange={(v) => setPriority(v as "low" | "normal" | "high")}
              disabled={formDisabled}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Low</SelectItem>
                <SelectItem value="normal">Normal</SelectItem>
                <SelectItem value="high">High</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Error message */}
          {error && (
            <div className="text-sm text-destructive bg-destructive/10 p-2 rounded">
              {error}
            </div>
          )}

          {/* Success message */}
          {success && (
            <div className="text-sm text-success bg-success/10 p-2 rounded">
              Message sent successfully!
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={sendMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={() => sendMutation.mutate()}
            disabled={!canSend || sendMutation.isPending || success}
          >
            {sendMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Sending...
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Send
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
