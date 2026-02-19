import { useState, useCallback, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import { Users, Clock, GitBranch, RefreshCw, User, Mail, Trash2, RotateCcw } from "lucide-react"
import { Card, CardContent } from "../components/ui/card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog"
import { SendMessageDialog } from "../components/SendMessageDialog"
import { Pagination } from "../components/Pagination"
import { type ApiClient, type WorkspacePresence } from "../lib/api"
import { useStore } from "../hooks/useStore"
import { cn, formatRelativeTime } from "../lib/utils"

const statusColors: Record<string, string> = {
  active: "bg-success",
  idle: "bg-muted-foreground",
  working: "bg-accent",
  offline: "bg-muted-foreground/50",
  unknown: "bg-muted-foreground",
}

function WorkspaceCard({
  workspace,
  onSendMessage,
  onDelete,
  onRestore,
}: {
  workspace: WorkspacePresence
  onSendMessage: (workspace: WorkspacePresence) => void
  onDelete: (workspace: WorkspacePresence) => void
  onRestore: (workspace: WorkspacePresence) => void
}) {
  const isDeleted = !!workspace.deleted_at

  return (
    <Card className={isDeleted ? "opacity-60" : undefined}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            {/* Alias & Status */}
            <div className="flex items-center gap-2 mb-1">
              <div
                className={cn(
                  "h-3 w-3 shrink-0 rounded-full",
                  isDeleted ? "bg-destructive/50" : (statusColors[workspace.status] || statusColors.unknown)
                )}
              />
              <span className="font-medium truncate">{workspace.alias}</span>
              {isDeleted ? (
                <Badge variant="destructive" className="text-xs shrink-0">
                  deleted
                </Badge>
              ) : (
                <Badge variant="outline" className="text-xs shrink-0">
                  {workspace.status}
                </Badge>
              )}
            </div>

            {/* Role (if set) */}
            {workspace.role && (
              <p className="text-xs text-muted-foreground mb-1 italic">
                {workspace.role}
              </p>
            )}

            {/* Metadata line */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {workspace.project_slug && (
                <>
                  <span className="px-1.5 py-0.5 bg-muted text-muted-foreground rounded">
                    {workspace.project_slug}
                  </span>
                  <span>·</span>
                </>
              )}
              {workspace.human_name && (
                <>
                  <span className="flex items-center gap-1">
                    <User className="h-3 w-3" />
                    {workspace.human_name}
                  </span>
                  <span>·</span>
                </>
              )}
              {workspace.repo && (
                <>
                  <span className="flex items-center gap-1 font-mono">
                    <GitBranch className="h-3 w-3" />
                    {workspace.repo}
                    {workspace.branch && `:${workspace.branch}`}
                  </span>
                </>
              )}
              {workspace.program && (
                <>
                  <span>·</span>
                  <span className="px-1.5 py-0.5 bg-secondary rounded">
                    {workspace.program}
                  </span>
                </>
              )}
              {workspace.last_seen && (
                <>
                  <span>·</span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(workspace.last_seen)}
                  </span>
                </>
              )}
            </div>

            {/* Workspace ID */}
            <p className="text-[10px] text-muted-foreground/60 font-mono mt-2 truncate">
              {workspace.workspace_id}
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex gap-2 shrink-0">
            {isDeleted ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRestore(workspace)}
                aria-label={`Restore workspace ${workspace.alias}`}
              >
                <RotateCcw className="h-4 w-4 mr-1" />
                Restore
              </Button>
            ) : (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => onSendMessage(workspace)}
                >
                  <Mail className="h-4 w-4" />
                  Message
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  onClick={() => onDelete(workspace)}
                  aria-label={`Delete workspace ${workspace.alias}`}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function WorkspacesPage() {
  const api = useApi<ApiClient>()
  const { repoFilter, ownerFilter } = useStore()
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>("online")
  const [messageDialogOpen, setMessageDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [restoreDialogOpen, setRestoreDialogOpen] = useState(false)
  const [selectedWorkspace, setSelectedWorkspace] = useState<WorkspacePresence | null>(null)
  const [allWorkspaces, setAllWorkspaces] = useState<WorkspacePresence[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  const handleSendMessage = (workspace: WorkspacePresence) => {
    setSelectedWorkspace(workspace)
    setMessageDialogOpen(true)
  }

  const handleDeleteClick = (workspace: WorkspacePresence) => {
    setSelectedWorkspace(workspace)
    setDeleteDialogOpen(true)
  }

  const handleRestoreClick = (workspace: WorkspacePresence) => {
    setSelectedWorkspace(workspace)
    setRestoreDialogOpen(true)
  }

  const deleteMutation = useMutation({
    mutationFn: (workspaceId: string) => api.deleteWorkspace(workspaceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] })
      queryClient.invalidateQueries({ queryKey: ["workspaces-deleted"] })
      setDeleteDialogOpen(false)
      setSelectedWorkspace(null)
    },
  })

  const restoreMutation = useMutation({
    mutationFn: (workspaceId: string) => api.restoreWorkspace(workspaceId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] })
      queryClient.invalidateQueries({ queryKey: ["workspaces-deleted"] })
      setRestoreDialogOpen(false)
      setSelectedWorkspace(null)
    },
  })

  const handleCloseDeleteDialog = (open: boolean) => {
    if (!open) {
      deleteMutation.reset()
    }
    setDeleteDialogOpen(open)
  }

  const handleCloseRestoreDialog = (open: boolean) => {
    if (!open) {
      restoreMutation.reset()
    }
    setRestoreDialogOpen(open)
  }

  const handleConfirmDelete = () => {
    if (selectedWorkspace) {
      deleteMutation.mutate(selectedWorkspace.workspace_id)
    }
  }

  const handleConfirmRestore = () => {
    if (selectedWorkspace) {
      restoreMutation.mutate(selectedWorkspace.workspace_id)
    }
  }

  // Query for active workspaces (not deleted)
  const {
    data: initialData,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: ["workspaces", repoFilter, ownerFilter],
    queryFn: () => api.listWorkspaces({
      repo: repoFilter || undefined,
      humanName: ownerFilter || undefined,
      limit: 50,
    }),
    refetchInterval: 30000,
    enabled: statusFilter !== "deleted",
  })

  // Query for deleted workspaces
  const {
    data: deletedData,
    isLoading: deletedLoading,
    error: deletedError,
    refetch: refetchDeleted,
  } = useQuery({
    queryKey: ["workspaces-deleted", repoFilter, ownerFilter],
    queryFn: () => api.listWorkspaces({
      repo: repoFilter || undefined,
      humanName: ownerFilter || undefined,
      includeDeleted: true,
      limit: 50,
    }),
    refetchInterval: 30000,
    enabled: statusFilter === "deleted",
  })

  // Sync local state from query data (handles both fresh fetches and cached data on remount)
  // Include filters in dependencies to ensure this runs when filters change, even if
  // initialData reference is the same (cached data)
  useEffect(() => {
    if (initialData) {
      setAllWorkspaces(initialData.workspaces)
      setNextCursor(initialData.next_cursor)
      setHasMore(initialData.has_more)
    }
  }, [initialData, repoFilter, ownerFilter])

  const handleLoadMore = useCallback(async () => {
    if (!nextCursor || isLoadingMore) return

    setIsLoadingMore(true)
    try {
      const result = await api.listWorkspaces({
        repo: repoFilter || undefined,
        humanName: ownerFilter || undefined,
        limit: 50,
        cursor: nextCursor,
      })
      setAllWorkspaces(prev => [...prev, ...result.workspaces])
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
    } finally {
      setIsLoadingMore(false)
    }
  }, [nextCursor, isLoadingMore, repoFilter, ownerFilter])

  // Calculate counts for tabs (from loaded workspaces)
  const onlineCount = allWorkspaces.filter(ws => ws.status !== "offline" && !ws.deleted_at).length
  const offlineCount = allWorkspaces.filter(ws => ws.status === "offline" && !ws.deleted_at).length
  const totalCount = allWorkspaces.filter(ws => !ws.deleted_at).length

  // For deleted tab, filter from deletedData
  const deletedWorkspaces = (deletedData?.workspaces || []).filter(ws => ws.deleted_at)
  const deletedCount = deletedWorkspaces.length

  // Filter workspaces based on status tab
  const filteredWorkspaces = statusFilter === "deleted"
    ? deletedWorkspaces
    : allWorkspaces.filter(ws => {
        if (ws.deleted_at) return false // Don't show deleted in active tabs
        if (statusFilter === "online") return ws.status !== "offline"
        if (statusFilter === "offline") return ws.status === "offline"
        return true // "all"
      })

  // Determine loading/error states based on current tab
  const currentLoading = statusFilter === "deleted" ? deletedLoading : isLoading
  const currentError = statusFilter === "deleted" ? deletedError : error
  const handleRefresh = statusFilter === "deleted" ? refetchDeleted : refetch

  // Build scope label
  const scopeLabel = ownerFilter
    ? `Owner: ${ownerFilter}`
    : repoFilter
    ? `Repo: ${repoFilter}`
    : "All workspaces"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Workspaces</h1>
          <p className="text-sm text-muted-foreground">{scopeLabel}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => handleRefresh()}
          disabled={currentLoading}
        >
          <RefreshCw className={cn("h-4 w-4", currentLoading && "animate-spin")} />
        </Button>
      </div>

      {/* Tabs */}
      <Tabs value={statusFilter} onValueChange={setStatusFilter}>
        <TabsList>
          <TabsTrigger value="online">Online ({onlineCount})</TabsTrigger>
          <TabsTrigger value="offline">Offline ({offlineCount})</TabsTrigger>
          <TabsTrigger value="all">All ({totalCount})</TabsTrigger>
          <TabsTrigger value="deleted">Deleted ({deletedCount})</TabsTrigger>
        </TabsList>

        <TabsContent value={statusFilter} className="mt-4">
          {/* Error State */}
          {currentError && (
            <Card className="border-destructive">
              <CardContent className="p-4">
                <p className="text-sm text-destructive">
                  Failed to load workspaces: {(currentError as Error).message}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Loading State */}
          {currentLoading && filteredWorkspaces.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              Loading workspaces...
            </div>
          )}

          {/* Empty State */}
          {filteredWorkspaces.length === 0 && !currentLoading && (
            <Card>
              <CardContent className="p-8 text-center">
                <Users className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  {statusFilter === "online"
                    ? "No online workspaces"
                    : statusFilter === "offline"
                    ? "No offline workspaces"
                    : statusFilter === "deleted"
                    ? "No deleted workspaces"
                    : repoFilter || ownerFilter
                    ? "No workspaces match the current filters"
                    : "No registered workspaces"}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Workspaces List */}
          {filteredWorkspaces.length > 0 && (
            <div className="grid gap-3">
              {filteredWorkspaces.map((workspace) => (
                <WorkspaceCard
                  key={workspace.workspace_id}
                  workspace={workspace}
                  onSendMessage={handleSendMessage}
                  onDelete={handleDeleteClick}
                  onRestore={handleRestoreClick}
                />
              ))}
            </div>
          )}

          {/* Pagination (only for active tabs, not deleted) */}
          {statusFilter !== "deleted" && (
            <Pagination
              onLoadMore={handleLoadMore}
              hasMore={hasMore}
              isLoading={isLoadingMore}
              itemCount={allWorkspaces.length}
            />
          )}
        </TabsContent>
      </Tabs>

      {/* Send Message Dialog */}
      <SendMessageDialog
        open={messageDialogOpen}
        onOpenChange={setMessageDialogOpen}
        targetWorkspaceId={selectedWorkspace?.workspace_id}
        targetAlias={selectedWorkspace?.alias}
      />

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onOpenChange={handleCloseDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Workspace</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete the workspace{" "}
              <span className="font-semibold">{selectedWorkspace?.alias}</span>?
              This will deregister the workspace from BeadHub. The alias can be
              reused after deletion.
            </DialogDescription>
          </DialogHeader>
          {deleteMutation.isError && (
            <p className="text-sm text-destructive">
              Failed to delete workspace: {(deleteMutation.error as Error).message}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => handleCloseDeleteDialog(false)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Restore Confirmation Dialog */}
      <Dialog open={restoreDialogOpen} onOpenChange={handleCloseRestoreDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Restore Workspace</DialogTitle>
            <DialogDescription>
              Restore the workspace{" "}
              <span className="font-semibold">{selectedWorkspace?.alias}</span>?
              This will reactivate the workspace in BeadHub.
            </DialogDescription>
          </DialogHeader>
          {restoreMutation.isError && (
            <p className="text-sm text-destructive">
              Failed to restore workspace: {(restoreMutation.error as Error).message}
            </p>
          )}
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => handleCloseRestoreDialog(false)}
              disabled={restoreMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={handleConfirmRestore}
              disabled={restoreMutation.isPending}
            >
              {restoreMutation.isPending ? "Restoring..." : "Restore"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
