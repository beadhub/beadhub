import { useState, useEffect, useCallback, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import {
  MessageSquare,
  Clock,
  Mail,
  MailOpen,
  RefreshCw,
  Check,
  AlertCircle,
  X,
} from "lucide-react"
import { Card, CardContent } from "../components/ui/card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs"
import { Pagination } from "../components/Pagination"
import { type ApiClient, type InboxMessage } from "../lib/api"
import { cn, formatRelativeTime } from "../lib/utils"

interface MessageWithWorkspace extends InboxMessage {
  workspace_id: string
  workspace_alias?: string
  project_slug?: string
}

function MessageCard({
  message,
  onClick,
  onWorkspaceClick,
}: {
  message: MessageWithWorkspace
  onClick: () => void
  onWorkspaceClick: (workspaceId: string) => void
}) {
  const priorityColors: Record<string, string> = {
    urgent: "text-destructive",
    high: "text-warning",
    normal: "text-foreground",
    low: "text-muted-foreground",
  }
  const priorityColor = priorityColors[message.priority] || "text-foreground"

  return (
    <Card
      className={cn(
        "cursor-pointer hover:border-primary/50 transition-colors",
        !message.read && "border-accent/50 bg-accent/5"
      )}
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              {message.read ? (
                <MailOpen className="h-4 w-4 text-muted-foreground shrink-0" />
              ) : (
                <Mail className="h-4 w-4 text-accent shrink-0" />
              )}
              <span className={cn("font-semibold", message.read && "text-muted-foreground")}>
                {message.from_alias}
              </span>
              <span className="text-xs text-muted-foreground flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatRelativeTime(message.created_at)}
              </span>
            </div>
            <h3 className={cn("font-medium truncate mb-1", !message.read && "font-semibold")}>
              {message.subject || "(no subject)"}
            </h3>
            {message.body && (
              <p className="text-sm text-muted-foreground line-clamp-2">
                {message.body}
              </p>
            )}
            <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
              {message.project_slug && (
                <>
                  <span className="px-1.5 py-0.5 bg-muted text-muted-foreground rounded">
                    {message.project_slug}
                  </span>
                  <span>·</span>
                </>
              )}
              <button
                className="hover:text-foreground hover:underline"
                onClick={(e) => {
                  e.stopPropagation()
                  onWorkspaceClick(message.workspace_id)
                }}
              >
                to {message.workspace_alias || message.workspace_id.slice(0, 8)}
              </button>
            </div>
          </div>
          <div className="flex flex-col items-end gap-2">
            {message.priority !== "normal" && (
              <Badge
                variant="outline"
                className={cn("text-xs", priorityColor)}
              >
                {message.priority}
              </Badge>
            )}
            {!message.read && (
              <div className="h-2 w-2 rounded-full bg-accent" />
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function MessageDetailDialog({
  message,
  open,
  onClose,
}: {
  message: MessageWithWorkspace | null
  open: boolean
  onClose: () => void
}) {
  const api = useApi<ApiClient>()
  const queryClient = useQueryClient()

  const ackMutation = useMutation({
    mutationFn: () => {
      if (!message) throw new Error("No message selected")
      return api.acknowledgeMessage(message.message_id, message.workspace_id)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-inboxes"] })
    },
  })

  const handleAck = () => {
    if (message && !message.read) {
      ackMutation.mutate()
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        {message ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {message.read ? (
                  <MailOpen className="h-5 w-5 text-muted-foreground" />
                ) : (
                  <Mail className="h-5 w-5 text-accent" />
                )}
                {message.subject || "(no subject)"}
              </DialogTitle>
              <DialogDescription>
                From <span className="font-mono">{message.from_alias}</span> to{" "}
                <span className="font-mono">{message.workspace_alias || message.workspace_id.slice(0, 8)}</span> ·{" "}
                {formatRelativeTime(message.created_at)}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              {message.priority !== "normal" && (
                <div className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-warning" />
                  <span className="text-sm font-medium capitalize">
                    {message.priority} priority
                  </span>
                </div>
              )}

              <div className="p-4 bg-secondary rounded-lg text-sm whitespace-pre-wrap">
                {message.body || "(empty message)"}
              </div>

              {message.thread_id && (
                <p className="text-xs text-muted-foreground">
                  Thread: <span className="font-mono">{message.thread_id}</span>
                </p>
              )}
            </div>

            <DialogFooter>
              <Button variant="ghost" onClick={onClose}>
                Close
              </Button>
              {!message.read && (
                <Button
                  onClick={handleAck}
                  disabled={ackMutation.isPending}
                >
                  <Check className="h-4 w-4 mr-2" />
                  {ackMutation.isPending ? "Marking..." : "Mark as Read"}
                </Button>
              )}
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

// Per-workspace pagination state
interface WorkspacePaginationState {
  cursor: string | null
  hasMore: boolean
}

export function MessagesPage() {
  const api = useApi<ApiClient>()
  const [selectedMessage, setSelectedMessage] = useState<MessageWithWorkspace | null>(null)
  const [filter, setFilter] = useState<string>("unread")
  const [workspaceFilter, setWorkspaceFilter] = useState<string | null>(null)
  const [allMessages, setAllMessages] = useState<MessageWithWorkspace[]>([])
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  // Track pagination state per workspace
  const paginationState = useRef<Map<string, WorkspacePaginationState>>(new Map())

  // Fetch all workspaces
  const { data: workspacesData } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.listWorkspaces(),
    staleTime: 60000,
  })

  const workspaces = workspacesData?.workspaces || []
  const workspaceMap = new Map(workspaces.map((ws) => [ws.workspace_id, ws]))

  // Fetch inboxes for all workspaces (always fetch all, filter client-side)
  const {
    data: queryData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["all-inboxes", workspaces.map((ws) => ws.workspace_id).join(",")],
    queryFn: async () => {
      if (workspaces.length === 0) return []

      const results = await Promise.all(
        workspaces.map(async (ws) => {
          try {
            const inbox = await api.fetchInbox(ws.workspace_id, {
              limit: 50,
            })
            // Track pagination state for this workspace
            paginationState.current.set(ws.workspace_id, {
              cursor: inbox.next_cursor,
              hasMore: inbox.has_more,
            })
            return inbox.messages.map((msg) => ({
              ...msg,
              workspace_id: ws.workspace_id,
              workspace_alias: ws.alias,
              project_slug: ws.project_slug || undefined,
            }))
          } catch {
            return []
          }
        })
      )

      // Flatten and sort by created_at desc
      const messages = results
        .flat()
        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())

      setAllMessages(messages)
      return messages
    },
    enabled: workspaces.length > 0,
    refetchInterval: 30000,
  })

  // Sync query data to local state (fixes navigation cache bug)
  useEffect(() => {
    if (queryData) {
      setAllMessages(queryData)
    }
  }, [queryData])

  // Check if any workspace has more messages
  const hasMore = Array.from(paginationState.current.values()).some(s => s.hasMore)

  // Load more messages from workspaces that have more
  const handleLoadMore = useCallback(async () => {
    if (isLoadingMore) return

    // Find workspaces with more messages
    const workspacesWithMore = workspaces.filter(ws => {
      const state = paginationState.current.get(ws.workspace_id)
      return state?.hasMore && state?.cursor
    })

    if (workspacesWithMore.length === 0) return

    setIsLoadingMore(true)
    try {
      const results = await Promise.all(
        workspacesWithMore.map(async (ws) => {
          const state = paginationState.current.get(ws.workspace_id)
          if (!state?.cursor) return []

          try {
            const inbox = await api.fetchInbox(ws.workspace_id, {
              limit: 50,
              cursor: state.cursor,
            })
            // Update pagination state
            paginationState.current.set(ws.workspace_id, {
              cursor: inbox.next_cursor,
              hasMore: inbox.has_more,
            })
            return inbox.messages.map((msg) => ({
              ...msg,
              workspace_id: ws.workspace_id,
              workspace_alias: ws.alias,
              project_slug: ws.project_slug || undefined,
            }))
          } catch {
            return []
          }
        })
      )

      const newMessages = results.flat()
      if (newMessages.length > 0) {
        setAllMessages(prev => {
          // Dedupe by message_id and sort
          const combined = [...prev, ...newMessages]
          const seen = new Set<string>()
          return combined
            .filter(msg => {
              if (seen.has(msg.message_id)) return false
              seen.add(msg.message_id)
              return true
            })
            .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        })
      }
    } finally {
      setIsLoadingMore(false)
    }
  }, [workspaces, isLoadingMore])

  // Apply filters (workspace + read status)
  const filteredMessages = allMessages?.filter((m) => {
    if (workspaceFilter && m.workspace_id !== workspaceFilter) return false
    if (filter === "unread" && m.read) return false
    return true
  })

  const unreadCount = allMessages?.filter((m) => !m.read).length ?? 0
  const selectedWorkspace = workspaceFilter ? workspaceMap.get(workspaceFilter) : null

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            Messages
            {unreadCount > 0 && (
              <Badge variant="default" className="ml-2">
                {unreadCount} unread
              </Badge>
            )}
          </h1>
          <p className="text-sm text-muted-foreground">
            {workspaceFilter ? (
              <span className="flex items-center gap-2">
                Filtering: <span className="font-mono">{selectedWorkspace?.alias || workspaceFilter.slice(0, 8)}</span>
                <button
                  className="hover:text-foreground"
                  onClick={() => setWorkspaceFilter(null)}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ) : (
              "All workspaces"
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw className={cn("h-4 w-4", isLoading && "animate-spin")} />
          </Button>
        </div>
      </div>

      <Tabs value={filter} onValueChange={setFilter}>
        <TabsList>
          <TabsTrigger value="unread">Unread</TabsTrigger>
          <TabsTrigger value="all">All</TabsTrigger>
        </TabsList>

        <TabsContent value={filter} className="mt-4">
          {error && (
            <Card className="border-destructive">
              <CardContent className="p-4">
                <p className="text-sm text-destructive">
                  Failed to load messages: {(error as Error).message}
                </p>
              </CardContent>
            </Card>
          )}

          {isLoading && allMessages.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              Loading messages...
            </div>
          )}

          {filteredMessages?.length === 0 && !isLoading && (
            <Card>
              <CardContent className="p-8 text-center">
                <MessageSquare className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  {filter === "unread" ? "No unread messages" : "No messages"}
                </p>
              </CardContent>
            </Card>
          )}

          {filteredMessages && filteredMessages.length > 0 && (
            <div className="grid gap-3">
              {filteredMessages.map((message) => (
                <MessageCard
                  key={`${message.workspace_id}-${message.message_id}`}
                  message={message}
                  onClick={() => setSelectedMessage(message)}
                  onWorkspaceClick={setWorkspaceFilter}
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          <Pagination
            onLoadMore={handleLoadMore}
            hasMore={hasMore}
            isLoading={isLoadingMore}
            itemCount={allMessages.length}
          />
        </TabsContent>
      </Tabs>

      <MessageDetailDialog
        message={selectedMessage}
        open={!!selectedMessage}
        onClose={() => setSelectedMessage(null)}
      />
    </div>
  )
}
