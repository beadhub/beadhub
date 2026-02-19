import { useState, useCallback, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import {
  AlertTriangle,
  Clock,
  CheckCircle,
  RefreshCw,
  MessageSquare,
  Send,
} from "lucide-react"
import { Card, CardContent } from "../components/ui/card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Textarea } from "../components/ui/textarea"
import { Input } from "../components/ui/input"
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
import { type ApiClient, type EscalationSummary } from "../lib/api"
import { useStore } from "../hooks/useStore"
import { cn, formatRelativeTime } from "../lib/utils"

function EscalationCard({
  escalation,
  onClick,
}: {
  escalation: EscalationSummary
  onClick: () => void
}) {
  const isPending = escalation.status === "pending"
  const isExpired =
    escalation.expires_at && new Date(escalation.expires_at) < new Date()

  return (
    <Card
      className={cn(
        "cursor-pointer hover:border-primary/50 transition-colors",
        isPending && "border-warning/50"
      )}
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              {isPending ? (
                <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
              ) : (
                <CheckCircle className="h-4 w-4 text-success shrink-0" />
              )}
              <h3 className="font-medium truncate">{escalation.subject}</h3>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>from {escalation.alias}</span>
              <span>·</span>
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {formatRelativeTime(escalation.created_at)}
              </span>
            </div>
          </div>
          <Badge
            variant={isPending ? "warning" : "secondary"}
            className={cn(isExpired && "bg-destructive text-destructive-foreground")}
          >
            {isExpired ? "expired" : escalation.status}
          </Badge>
        </div>
      </CardContent>
    </Card>
  )
}

function EscalationDetailDialog({
  escalationId,
  open,
  onClose,
}: {
  escalationId: string | null
  open: boolean
  onClose: () => void
}) {
  const api = useApi<ApiClient>()
  const queryClient = useQueryClient()
  const [response, setResponse] = useState("")
  const [note, setNote] = useState("")

  const { data: detail, isLoading } = useQuery({
    queryKey: ["escalation", escalationId],
    queryFn: () => (escalationId ? api.getEscalation(escalationId) : null),
    enabled: !!escalationId && open,
  })

  const respondMutation = useMutation({
    mutationFn: () =>
      api.respondToEscalation(escalationId!, response, note || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["escalations"] })
      queryClient.invalidateQueries({ queryKey: ["escalation", escalationId] })
      setResponse("")
      setNote("")
      onClose()
    },
  })

  const handleQuickResponse = (text: string) => {
    setResponse(text)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        {isLoading ? (
          <div className="py-8 text-center text-muted-foreground">
            Loading...
          </div>
        ) : detail ? (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <AlertTriangle
                  className={cn(
                    "h-5 w-5",
                    detail.status === "pending" ? "text-warning" : "text-success"
                  )}
                />
                {detail.subject}
              </DialogTitle>
              <DialogDescription>
                From <span className="font-mono">{detail.alias}</span> ·{" "}
                {formatRelativeTime(detail.created_at)}
              </DialogDescription>
            </DialogHeader>

            {/* Situation */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">Situation</h4>
              <div className="p-3 bg-secondary rounded-lg text-sm whitespace-pre-wrap">
                {detail.situation}
              </div>
            </div>

            {/* Options (if provided) */}
            {detail.options && detail.options.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-medium">Suggested Options</h4>
                <div className="flex flex-wrap gap-2">
                  {detail.options.map((option, i) => (
                    <Button
                      key={i}
                      variant="outline"
                      size="sm"
                      onClick={() => handleQuickResponse(option)}
                      disabled={detail.status !== "pending"}
                    >
                      {option}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            {/* Response section */}
            {detail.status === "pending" ? (
              <div className="space-y-3 pt-4 border-t">
                <h4 className="text-sm font-medium">Your Response</h4>
                <Textarea
                  placeholder="Type your response..."
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  rows={3}
                />
                <Input
                  placeholder="Optional note (internal)"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                />
              </div>
            ) : (
              <div className="space-y-2 pt-4 border-t">
                <h4 className="text-sm font-medium">Response</h4>
                <div className="p-3 bg-success/10 rounded-lg text-sm">
                  {detail.response}
                </div>
                {detail.response_note && (
                  <p className="text-xs text-muted-foreground">
                    Note: {detail.response_note}
                  </p>
                )}
                {detail.responded_at && (
                  <p className="text-xs text-muted-foreground">
                    Responded {formatRelativeTime(detail.responded_at)}
                  </p>
                )}
              </div>
            )}

            {detail.status === "pending" && (
              <DialogFooter>
                <Button variant="ghost" onClick={onClose}>
                  Cancel
                </Button>
                <Button
                  onClick={() => respondMutation.mutate()}
                  disabled={!response.trim() || respondMutation.isPending}
                >
                  <Send className="h-4 w-4 mr-2" />
                  {respondMutation.isPending ? "Sending..." : "Send Response"}
                </Button>
              </DialogFooter>
            )}
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

export function EscalationsPage() {
  const api = useApi<ApiClient>()
  const { repoFilter } = useStore()
  const [selectedEscalationId, setSelectedEscalationId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>("pending")
  const [allEscalations, setAllEscalations] = useState<EscalationSummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  // Build filters for the API (priority: repo > project)
  const scopeFilters = repoFilter
    ? { repo: repoFilter }
    : {}
  const filters = {
    ...scopeFilters,
    ...(statusFilter ? { status: statusFilter } : {}),
  }

  const {
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["escalations", filters],
    queryFn: async () => {
      const result = await api.listEscalations({
        ...filters,
        limit: 50,
      })
      setAllEscalations(result.escalations)
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
      return result
    },
    refetchInterval: 30000,
  })

  // Reset pagination when filters change
  useEffect(() => {
    setAllEscalations([])
    setNextCursor(null)
    setHasMore(false)
  }, [repoFilter, statusFilter])

  const handleLoadMore = useCallback(async () => {
    if (!nextCursor || isLoadingMore) return

    setIsLoadingMore(true)
    try {
      const result = await api.listEscalations({
        ...filters,
        limit: 50,
        cursor: nextCursor,
      })
      setAllEscalations(prev => [...prev, ...result.escalations])
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
    } finally {
      setIsLoadingMore(false)
    }
  }, [nextCursor, isLoadingMore, filters])

  // Build scope label
  const scopeLabel = repoFilter
    ? `Repo: ${repoFilter}`
    : "All workspaces"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Escalations</h1>
          <p className="text-sm text-muted-foreground">{scopeLabel}</p>
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

      {/* Tabs */}
      <Tabs value={statusFilter} onValueChange={setStatusFilter}>
        <TabsList>
          <TabsTrigger value="pending">Pending</TabsTrigger>
          <TabsTrigger value="responded">Responded</TabsTrigger>
          <TabsTrigger value="">All</TabsTrigger>
        </TabsList>

        <TabsContent value={statusFilter} className="mt-4">
          {/* Error State */}
          {error && (
            <Card className="border-destructive">
              <CardContent className="p-4">
                <p className="text-sm text-destructive">
                  Failed to load escalations: {(error as Error).message}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Loading State */}
          {isLoading && allEscalations.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              Loading escalations...
            </div>
          )}

          {/* Empty State */}
          {allEscalations.length === 0 && !isLoading && (
            <Card>
              <CardContent className="p-8 text-center">
                <MessageSquare className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  {statusFilter === "pending"
                    ? "No pending escalations"
                    : "No escalations found"}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Escalations List */}
          {allEscalations.length > 0 && (
            <div className="grid gap-3">
              {allEscalations.map((escalation) => (
                <EscalationCard
                  key={escalation.escalation_id}
                  escalation={escalation}
                  onClick={() =>
                    setSelectedEscalationId(escalation.escalation_id)
                  }
                />
              ))}
            </div>
          )}

          {/* Pagination */}
          <Pagination
            onLoadMore={handleLoadMore}
            hasMore={hasMore}
            isLoading={isLoadingMore}
            itemCount={allEscalations.length}
          />
        </TabsContent>
      </Tabs>

      {/* Detail Dialog */}
      <EscalationDetailDialog
        escalationId={selectedEscalationId}
        open={!!selectedEscalationId}
        onClose={() => setSelectedEscalationId(null)}
      />
    </div>
  )
}
