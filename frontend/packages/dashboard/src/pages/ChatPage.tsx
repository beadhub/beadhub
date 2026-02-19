import { useState, useEffect, useRef, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import {
  MessageCircle,
  RefreshCw,
  Send,
  X,
  Users,
  History,
  ArrowLeft,
  AlertTriangle,
  Plus,
  Eye,
  UserPlus,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Input } from "../components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs"
import { StartChatDialog } from "../components/StartChatDialog"
import { ChatBubble } from "../components/ChatBubble"
import { Pagination } from "../components/Pagination"
import {
  type ApiClient,
  type ChatMessage,
  type MessageHistoryItem,
  type StartChatResponse,
  type AdminSessionListItem,
} from "../lib/api"
import { cn, formatRelativeTime } from "../lib/utils"
import { useStore } from "../hooks/useStore"

function SessionCard({
  session,
  myAlias,
  onClick,
}: {
  session: AdminSessionListItem
  myAlias: string
  onClick: () => void
}) {
  const participantNames = session.participants.map(p => p.alias)
  const isParticipant = participantNames.includes(myAlias)

  return (
    <Card
      className="cursor-pointer hover:bg-secondary/50 transition-colors"
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Users className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="font-medium text-sm">
                {participantNames.join(" ↔ ")}
              </span>
              {!isParticipant && (
                <Badge variant="outline" className="text-xs">
                  <Eye className="h-3 w-3 mr-1" />
                  Observer
                </Badge>
              )}
            </div>
            {session.last_message && (
              <p className="text-sm text-muted-foreground mt-2 whitespace-pre-wrap line-clamp-2">
                <span className="font-medium">{session.last_from}:</span> {session.last_message}
              </p>
            )}
            <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
              {session.last_activity && (
                <span>{formatRelativeTime(session.last_activity)}</span>
              )}
              <span>{session.message_count} messages</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function AgentSessionGroup({
  agent,
  sessions,
  onSelectSession,
}: {
  agent: string
  sessions: AdminSessionListItem[]
  onSelectSession: (session: AdminSessionListItem) => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <Card>
      <CardHeader
        className="cursor-pointer py-3"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-2">
            <Users className="h-4 w-4" />
            {agent}
          </CardTitle>
          <Badge variant="secondary">{sessions.length} sessions</Badge>
        </div>
      </CardHeader>
      {expanded && (
        <CardContent className="pt-0 space-y-2">
          {sessions.map((session) => (
            <div
              key={session.session_id}
              className="p-3 rounded border cursor-pointer hover:bg-secondary/50 transition-colors"
              onClick={() => onSelectSession(session)}
            >
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium">
                  {session.participants.map(p => p.alias).filter(a => a !== agent).join(", ") || "Self"}
                </span>
                {session.message_count > 0 && (
                  <span className="text-xs text-muted-foreground">
                    ({session.message_count} msgs)
                  </span>
                )}
              </div>
              {session.last_message && (
                <p className="text-xs text-muted-foreground mt-1 line-clamp-1">
                  {session.last_message}
                </p>
              )}
            </div>
          ))}
        </CardContent>
      )}
    </Card>
  )
}

function SessionViewer({
  session,
  messages,
  myAlias,
  workspaceId,
  isParticipant,
  onBack,
  onJoined,
}: {
  session: AdminSessionListItem
  messages: MessageHistoryItem[]
  myAlias: string
  workspaceId: string
  isParticipant: boolean
  onBack: () => void
  onJoined: () => void
}) {
  const api = useApi<ApiClient>()
  const [inputValue, setInputValue] = useState("")
  const [isSending, setIsSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [deliveryWarning, setDeliveryWarning] = useState<string | null>(null)
  const [isJoining, setIsJoining] = useState(false)
  const [joined, setJoined] = useState(isParticipant)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const participantNames = session.participants.map(p => p.alias)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleJoin = async () => {
    setIsJoining(true)
    try {
      await api.joinSession(session.session_id, workspaceId, myAlias)
      setJoined(true)
      onJoined()
    } catch (error) {
      console.error("Failed to join session:", error)
      setSendError(error instanceof Error ? error.message : "Failed to join session")
    } finally {
      setIsJoining(false)
    }
  }

  const handleSend = async () => {
    if (!inputValue.trim() || isSending || !joined) return

    const message = inputValue.trim()
    setInputValue("")
    setIsSending(true)
    setSendError(null)
    setDeliveryWarning(null)

    try {
      const result = await api.sendChatMessage(session.session_id, workspaceId, myAlias, message)
      if (!result.delivered) {
        setDeliveryWarning("Message sent but not all recipients are online")
      }
      onJoined() // Refresh messages
    } catch (error) {
      console.error("Failed to send message:", error)
      setInputValue(message)
      setSendError(error instanceof Error ? error.message : "Failed to send message")
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
        <div>
          <h2 className="font-medium flex items-center gap-2">
            {participantNames.join(" ↔ ")}
            {!joined && (
              <Badge variant="outline">
                <Eye className="h-3 w-3 mr-1" />
                Observing
              </Badge>
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            {session.message_count} messages
          </p>
        </div>
      </div>

      <Card className="flex flex-col" style={{ height: "calc(100vh - 280px)", minHeight: "400px" }}>
        <CardContent className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
          {messages.length === 0 && (
            <p className="text-center text-muted-foreground py-8">
              No messages in this session
            </p>
          )}
          {messages.map((msg) => {
            // First participant = left, everyone else = right
            const alignRight = participantNames.length >= 1 && msg.from_agent !== participantNames[0]
            return (
              <ChatBubble
                key={msg.message_id}
                fromAlias={msg.from_agent}
                body={msg.body}
                timestamp={msg.created_at}
                alignRight={alignRight}
              />
            )
          })}
          <div ref={messagesEndRef} />
        </CardContent>

        <div className="flex-none p-4 border-t">
          {sendError && (
            <div className="flex items-center gap-2 mb-2 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{sendError}</span>
            </div>
          )}

          {deliveryWarning && (
            <div className="flex items-center gap-2 mb-2 text-sm text-warning">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>{deliveryWarning}</span>
            </div>
          )}

          {!joined ? (
            <Button onClick={handleJoin} disabled={isJoining} className="w-full">
              <UserPlus className="h-4 w-4 mr-2" />
              {isJoining ? "Joining..." : "Join & Reply"}
            </Button>
          ) : (
            <div className="flex gap-2">
              <Input
                value={inputValue}
                onChange={(e) => {
                  setInputValue(e.target.value)
                  if (sendError) setSendError(null)
                  if (deliveryWarning) setDeliveryWarning(null)
                }}
                onKeyDown={handleKeyDown}
                placeholder="Type a message..."
                disabled={isSending}
              />
              <Button onClick={handleSend} disabled={!inputValue.trim() || isSending}>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}

interface ActiveChatState {
  sessionId: string
  sseUrl: string
  otherAlias: string
  myAlias: string
  initialMessages: ChatMessage[]
}

function ActiveChatPanel({
  chat,
  workspaceId,
  onEnd,
}: {
  chat: ActiveChatState
  workspaceId: string
  onEnd: () => void
}) {
  const api = useApi<ApiClient>()
  const [messages, setMessages] = useState<ChatMessage[]>(chat.initialMessages)
  const [inputValue, setInputValue] = useState("")
  const [isConnected, setIsConnected] = useState(false)
  const [isSending, setIsSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [deliveryWarning, setDeliveryWarning] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const mountedRef = useRef(true)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  useEffect(() => {
    if (!chat.sseUrl) return

    const url = `${chat.sseUrl}${chat.sseUrl.includes("?") ? "&" : "?"}workspace_id=${encodeURIComponent(workspaceId)}`
    const controller = new AbortController()
    abortRef.current = controller

    ;(async () => {
      try {
        const response = await fetch(url, {
          headers: api.getHeaders(),
          signal: controller.signal,
        })
        if (!response.ok || !response.body) {
          if (mountedRef.current) setIsConnected(false)
          return
        }
        if (mountedRef.current) setIsConnected(true)

        const reader = response.body.getReader()
        const decoder = new TextDecoder("utf-8")
        let buffer = ""

        while (true) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n")

          while (true) {
            const idx = buffer.indexOf("\n\n")
            if (idx === -1) break
            const frame = buffer.slice(0, idx)
            buffer = buffer.slice(idx + 2)

            const dataLines = frame
              .split("\n")
              .filter((l) => l.startsWith("data:"))
              .map((l) => l.slice(5).trimStart())
            if (dataLines.length === 0) continue

            const raw = dataLines.join("\n")
            try {
              const data = JSON.parse(raw)
              if (data.type === "message") {
                setMessages((prev) => [
                  ...prev,
                  {
                    message_id: data.message_id,
                    from_alias: data.from_agent || data.from_alias,
                    body: data.body,
                    timestamp: data.timestamp || new Date().toISOString(),
                    sender_leaving: data.sender_leaving,
                  },
                ])
              }
            } catch (error) {
              console.error("Failed to parse SSE message:", error, raw)
            }
          }
        }
      } catch {
        if (controller.signal.aborted) return
        if (mountedRef.current) setIsConnected(false)
      }
    })()

    return () => {
      mountedRef.current = false
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
    }
  }, [chat.sseUrl, workspaceId, onEnd])

  const handleSend = async () => {
    if (!inputValue.trim() || isSending) return

    const message = inputValue.trim()
    setInputValue("")
    setIsSending(true)
    setSendError(null)
    setDeliveryWarning(null)

    try {
      const result = await api.sendChatMessage(chat.sessionId, workspaceId, chat.myAlias, message)
      if (!result.delivered) {
        setDeliveryWarning("Message sent but not all recipients are online")
      }
    } catch (error) {
      console.error("Failed to send message:", error)
      setInputValue(message)
      setSendError(error instanceof Error ? error.message : "Failed to send message")
    } finally {
      setIsSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <Card className="flex flex-col h-[600px]">
      <CardHeader className="flex-none border-b">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2">
            <MessageCircle className="h-5 w-5" />
            Chat with {chat.otherAlias}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Badge variant={isConnected ? "default" : "secondary"}>
              {isConnected ? "Connected" : "Connecting..."}
            </Badge>
            <Button variant="ghost" size="sm" onClick={onEnd}>
              <X className="h-4 w-4 mr-1" />
              Close
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
        {messages.length === 0 && (
          <p className="text-center text-muted-foreground py-8">
            Chat started. Waiting for messages...
          </p>
        )}
        {messages.map((msg) => (
          <ChatBubble
            key={msg.message_id}
            fromAlias={msg.from_alias}
            body={msg.body}
            timestamp={msg.timestamp}
            alignRight={msg.from_alias === chat.myAlias}
            senderLeaving={msg.sender_leaving}
          />
        ))}
        <div ref={messagesEndRef} />
      </CardContent>

      <div className="flex-none p-4 border-t">
        {sendError && (
          <div className="flex items-center gap-2 mb-2 text-sm text-destructive">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{sendError}</span>
          </div>
        )}
        {deliveryWarning && (
          <div className="flex items-center gap-2 mb-2 text-sm text-warning">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{deliveryWarning}</span>
          </div>
        )}
        <div className="flex gap-2">
          <Input
            value={inputValue}
            onChange={(e) => {
              setInputValue(e.target.value)
              if (sendError) setSendError(null)
              if (deliveryWarning) setDeliveryWarning(null)
            }}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            disabled={!isConnected || isSending}
          />
          <Button onClick={handleSend} disabled={!inputValue.trim() || isSending}>
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </Card>
  )
}

export function ChatPage() {
  const api = useApi<ApiClient>()
  const queryClient = useQueryClient()
  const { dashboardIdentity, identityLoading, identityError } = useStore()
  const [activeChat, setActiveChat] = useState<ActiveChatState | null>(null)
  const [viewingSession, setViewingSession] = useState<AdminSessionListItem | null>(null)
  const [startChatDialogOpen, setStartChatDialogOpen] = useState(false)
  const [allSessions, setAllSessions] = useState<AdminSessionListItem[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  const workspaceId = dashboardIdentity?.workspace_id || ""
  const myAlias = dashboardIdentity?.alias || ""

  // Fetch workspaces to get project_slug
  const { data: workspacesData } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.listWorkspaces(),
    staleTime: 60000,
    enabled: !!workspaceId,
  })

  const projectSlug = workspacesData?.workspaces?.find((ws) => ws.project_slug)?.project_slug

  // Reset pagination when workspaceId changes
  useEffect(() => {
    setAllSessions([])
    setNextCursor(null)
    setHasMore(false)
  }, [workspaceId])

  // Fetch ALL sessions in the project using admin endpoint
  const {
    data: queryData,
    isLoading: sessionsLoading,
    error: sessionsError,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: ["admin-sessions", workspaceId],
    queryFn: async () => {
      if (!workspaceId) {
        return { sessions: [], has_more: false, next_cursor: null }
      }
      const result = await api.listAllSessions(workspaceId, { limit: 50 })
      setAllSessions(result.sessions)
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
      return result
    },
    enabled: !!workspaceId,
    refetchInterval: activeChat ? false : 10000,
  })

  // Sync query data to local state (fixes navigation cache bug)
  useEffect(() => {
    if (queryData) {
      setAllSessions(queryData.sessions)
      setNextCursor(queryData.next_cursor)
      setHasMore(queryData.has_more)
    }
  }, [queryData])

  const handleLoadMore = useCallback(async () => {
    if (!nextCursor || isLoadingMore || !workspaceId) return

    setIsLoadingMore(true)
    try {
      const result = await api.listAllSessions(workspaceId, {
        limit: 50,
        cursor: nextCursor,
      })
      setAllSessions(prev => [...prev, ...result.sessions])
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
    } finally {
      setIsLoadingMore(false)
    }
  }, [nextCursor, isLoadingMore, workspaceId])

  // Fetch messages for the viewing session using admin endpoint
  const {
    data: messagesData,
    isLoading: messagesLoading,
    refetch: refetchMessages,
  } = useQuery({
    queryKey: ["admin-session-messages", viewingSession?.session_id, workspaceId],
    queryFn: () => {
      if (!viewingSession || !workspaceId) {
        return { session_id: "", messages: [] }
      }
      return api.getSessionMessagesAdmin(viewingSession.session_id, workspaceId)
    },
    enabled: !!viewingSession && !!workspaceId,
    refetchInterval: viewingSession ? 3000 : false, // Poll for new messages when viewing
  })

  const handleEndSession = () => {
    setActiveChat(null)
    refetchSessions()
  }

  const handleChatStarted = (response: StartChatResponse, targetAlias: string) => {
    setActiveChat({
      sessionId: response.session_id,
      sseUrl: response.sse_url,
      otherAlias: targetAlias,
      myAlias: myAlias,
      initialMessages: [],
    })
    queryClient.invalidateQueries({ queryKey: ["admin-sessions"] })
  }

  const sessions = allSessions

  // Group sessions by agent for "By Agent" tab
  const sessionsByAgent = sessions.reduce((acc, session) => {
    session.participants.forEach(p => {
      if (!acc[p.alias]) {
        acc[p.alias] = []
      }
      if (!acc[p.alias].includes(session)) {
        acc[p.alias].push(session)
      }
    })
    return acc
  }, {} as Record<string, AdminSessionListItem[]>)

  // Sort agents by session count (most active first)
  const sortedAgents = Object.entries(sessionsByAgent)
    .sort(([, a], [, b]) => b.length - a.length)
    .map(([agent]) => agent)

  // Check if user is a participant in the viewing session
  const isParticipant = viewingSession
    ? viewingSession.participants.some(p => p.alias === myAlias)
    : false

  if (activeChat && workspaceId) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Active Chat</h1>
            <p className="text-sm text-muted-foreground">
              Session {activeChat.sessionId.slice(0, 12)}...
            </p>
          </div>
          <Button variant="ghost" onClick={handleEndSession}>
            <X className="h-4 w-4 mr-2" />
            Close
          </Button>
        </div>

        <ActiveChatPanel
          chat={activeChat}
          workspaceId={workspaceId}
          onEnd={handleEndSession}
        />
      </div>
    )
  }

  if (viewingSession) {
    return (
      <div className="space-y-6">
        <h1 className="text-xl font-semibold">Chat Monitor</h1>
        {messagesLoading ? (
          <Card>
            <CardContent className="p-8 text-center">
              <RefreshCw className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
              <p className="text-muted-foreground mt-2">Loading messages...</p>
            </CardContent>
          </Card>
        ) : (
          <SessionViewer
            session={viewingSession}
            messages={messagesData?.messages || []}
            myAlias={myAlias}
            workspaceId={workspaceId}
            isParticipant={isParticipant}
            onBack={() => setViewingSession(null)}
            onJoined={() => {
              refetchMessages()
              refetchSessions()
            }}
          />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2">
            Chat Monitor
            {sessions.length > 0 && (
              <Badge variant="secondary">{sessions.length} sessions</Badge>
            )}
          </h1>
          <p className="text-sm text-muted-foreground">
            {dashboardIdentity ? (
              <>
                {projectSlug && (
                  <span className="px-1.5 py-0.5 bg-muted text-muted-foreground rounded mr-2">
                    {projectSlug}
                  </span>
                )}
                Monitoring as: {dashboardIdentity.alias}
              </>
            ) : identityLoading ? (
              "Loading..."
            ) : (
              "No workspace available"
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="default"
            size="sm"
            onClick={() => setStartChatDialogOpen(true)}
            disabled={!dashboardIdentity || identityLoading || !!identityError}
          >
            <Plus className="h-4 w-4 mr-1" />
            New Chat
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetchSessions()}
            disabled={sessionsLoading}
          >
            <RefreshCw className={cn("h-4 w-4", sessionsLoading && "animate-spin")} />
          </Button>
        </div>
      </div>

      {!dashboardIdentity && !identityLoading && (
        <Card>
          <CardContent className="p-8 text-center">
            <MessageCircle className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
            <p className="text-muted-foreground">
              No workspaces available. Chat requires an active workspace.
            </p>
          </CardContent>
        </Card>
      )}

      {sessionsError && (
        <Card className="border-destructive">
          <CardContent className="p-4">
            <p className="text-sm text-destructive">
              Failed to load sessions: {(sessionsError as Error).message}
            </p>
          </CardContent>
        </Card>
      )}

      {dashboardIdentity && (
        <Tabs defaultValue="all">
          <TabsList>
            <TabsTrigger value="all" className="gap-2">
              <MessageCircle className="h-4 w-4" />
              All Sessions
              {sessions.length > 0 && (
                <Badge variant="secondary" className="ml-1">{sessions.length}</Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="by-agent" className="gap-2">
              <Users className="h-4 w-4" />
              By Agent
              {sortedAgents.length > 0 && (
                <Badge variant="secondary" className="ml-1">{sortedAgents.length}</Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="all" className="space-y-4 mt-4">
            {sessions.length === 0 && !sessionsLoading && (
              <Card>
                <CardContent className="p-8 text-center">
                  <History className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">No chat sessions in this project</p>
                  <p className="text-xs text-muted-foreground mt-2">
                    Start a new chat or wait for agents to communicate
                  </p>
                </CardContent>
              </Card>
            )}

            {sessions.length > 0 && (
              <div className="grid gap-3">
                {sessions.map((session) => (
                  <SessionCard
                    key={session.session_id}
                    session={session}
                    myAlias={myAlias}
                    onClick={() => setViewingSession(session)}
                  />
                ))}
              </div>
            )}

            {/* Pagination */}
            <Pagination
              onLoadMore={handleLoadMore}
              hasMore={hasMore}
              isLoading={isLoadingMore}
              itemCount={sessions.length}
            />
          </TabsContent>

          <TabsContent value="by-agent" className="space-y-4 mt-4">
            {sortedAgents.length === 0 && !sessionsLoading && (
              <Card>
                <CardContent className="p-8 text-center">
                  <Users className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                  <p className="text-muted-foreground">No agents with chat sessions</p>
                </CardContent>
              </Card>
            )}

            {sortedAgents.length > 0 && (
              <div className="grid gap-3">
                {sortedAgents.map((agent) => (
                  <AgentSessionGroup
                    key={agent}
                    agent={agent}
                    sessions={sessionsByAgent[agent]}
                    onSelectSession={setViewingSession}
                  />
                ))}
              </div>
            )}

            {/* Pagination */}
            <Pagination
              onLoadMore={handleLoadMore}
              hasMore={hasMore}
              isLoading={isLoadingMore}
              itemCount={sessions.length}
            />
          </TabsContent>
        </Tabs>
      )}

      <StartChatDialog
        open={startChatDialogOpen}
        onOpenChange={setStartChatDialogOpen}
        onChatStarted={handleChatStarted}
      />
    </div>
  )
}
