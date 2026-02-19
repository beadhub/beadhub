import { useState, useMemo, useCallback, useEffect, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { useSearchParams } from "react-router-dom"
import { useApi } from "../hooks/useApi"
import {
  ListTodo,
  RefreshCw,
  User,
  ChevronRight,
  ChevronDown,
  ChevronsUpDown,
  Search,
  X,
  Clock,
  Calendar,
  Copy,
  Check,
} from "lucide-react"
import { Card, CardContent } from "../components/ui/card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select"
import { Input } from "../components/ui/input"
import { IssueDetailSheet } from "../components/IssueDetailSheet"
import { Pagination } from "../components/Pagination"
import { type ApiClient, type BeadIssue } from "../lib/api"
import { useStore } from "../hooks/useStore"
import { cn, formatRelativeTime } from "../lib/utils"

type SortedIssue = BeadIssue & {
  _indentLevel: number
  _hasChildren: boolean
  _parentId?: string
}

const issueTypes = [
  { value: "all", label: "All types" },
  { value: "bug", label: "Bug" },
  { value: "feature", label: "Feature" },
  { value: "task", label: "Task" },
  { value: "epic", label: "Epic" },
  { value: "chore", label: "Chore" },
]

const viewModes = [
  { value: "flat", label: "Flat" },
  { value: "tree", label: "Tree" },
]

const sortOrders = [
  { value: "priority", label: "Priority" },
  { value: "recent", label: "Recent" },
  { value: "oldest", label: "Oldest" },
]

const priorityStyles: Record<number, string> = {
  0: "text-destructive border-destructive",
  1: "text-warning border-warning",
  2: "text-foreground",
  3: "text-muted-foreground",
  4: "text-muted-foreground/50",
}

const statusColors: Record<string, string> = {
  open: "bg-green-500",
  in_progress: "bg-blue-500",
  closed: "bg-purple-500",
}

function IssueCard({
  issue,
  onSelect,
  onSelectCreator,
  indentLevel = 0,
  hasChildren = false,
  isCollapsed = false,
  onToggleCollapse,
}: {
  issue: BeadIssue
  onSelect: (issue: BeadIssue) => void
  onSelectCreator?: (creator: string) => void
  indentLevel?: number
  hasChildren?: boolean
  isCollapsed?: boolean
  onToggleCollapse?: () => void
}) {
  const [copied, setCopied] = useState(false)
  const copyTimeoutRef = useRef<number | null>(null)
  const hasBlockers = issue.blocked_by && issue.blocked_by.length > 0

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    }
  }, [])

  const handleCopyId = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(issue.bead_id)
      setCopied(true)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = window.setTimeout(() => setCopied(false), 1500)
    } catch (err) {
      console.error("Failed to copy bead ID:", err)
    }
  }

  return (
    <Card className={cn(indentLevel > 0 && "border-l-2 border-l-muted-foreground/30")}>
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              {hasChildren ? (
                <button
                  onClick={onToggleCollapse}
                  className="p-0.5 -ml-1 rounded hover:bg-muted transition-colors"
                  aria-label={isCollapsed ? "Expand" : "Collapse"}
                >
                  {isCollapsed ? (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                </button>
              ) : indentLevel > 0 ? (
                <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground/40 ml-0.5" />
              ) : null}
              <div
                className={cn(
                  "h-2.5 w-2.5 shrink-0 rounded-full",
                  statusColors[issue.status] || "bg-muted-foreground"
                )}
              />
              <h3
                className="text-sm font-medium truncate cursor-pointer hover:text-primary hover:underline"
                onClick={() => onSelect(issue)}
              >
                {issue.title}
              </h3>
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <Badge
                variant="outline"
                className="font-mono text-xs cursor-pointer hover:bg-accent hover:text-accent-foreground group/badge"
                onClick={handleCopyId}
                title="Click to copy bead ID"
              >
                {issue.bead_id}
                {copied ? (
                  <Check className="h-3 w-3 ml-1.5 text-green-500" />
                ) : (
                  <Copy className="h-3 w-3 ml-1.5 opacity-40 group-hover/badge:opacity-100" />
                )}
              </Badge>
              <span>·</span>
              <span className="font-mono">{issue.repo}</span>
              {issue.type && (
                <>
                  <span>·</span>
                  <span>{issue.type}</span>
                </>
              )}
              {issue.assignee && (
                <>
                  <span>·</span>
                  <span className="flex items-center gap-1">
                    <User className="h-3 w-3" />
                    {issue.assignee}
                  </span>
                </>
              )}
              {issue.created_by && (
                <>
                  <span>·</span>
                  <button
                    type="button"
                    className="flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer"
                    onClick={() => onSelectCreator?.(issue.created_by!)}
                    title={`Filter by creator: ${issue.created_by}`}
                  >
                    <User className="h-3 w-3" />
                    {issue.created_by}
                  </button>
                </>
              )}
              {hasBlockers && (
                <>
                  <span>·</span>
                  <span className="text-warning">
                    blocked by {issue.blocked_by.length}
                  </span>
                </>
              )}
              {issue.created_at && (
                <>
                  <span>·</span>
                  <span className="flex items-center gap-1" title={new Date(issue.created_at).toLocaleString()}>
                    <Calendar className="h-3 w-3" />
                    {formatRelativeTime(issue.created_at)}
                  </span>
                </>
              )}
              {issue.updated_at && (
                <>
                  <span>·</span>
                  <span className="flex items-center gap-1" title={new Date(issue.updated_at).toLocaleString()}>
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(issue.updated_at)}
                  </span>
                </>
              )}
            </div>
            {issue.labels && issue.labels.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {issue.labels.map((label) => (
                  <Badge key={label} variant="secondary" className="text-xs">
                    {label}
                  </Badge>
                ))}
              </div>
            )}
          </div>
          <Badge
            variant="outline"
            className={cn(
              priorityStyles[issue.priority]
            )}
          >
            P{issue.priority}
          </Badge>
        </div>
      </CardContent>
    </Card>
  )
}

const DEBOUNCE_MS = 300

export function IssuesPage() {
  const api = useApi<ApiClient>()
  const { repoFilter, createdByFilter, setCreatedByFilter } = useStore()
  const [searchParams, setSearchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState<string>("active")
  const [typeFilter, setTypeFilter] = useState<string>("all")
  const [viewMode, setViewMode] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("beads-view-mode") || "flat"
    }
    return "flat"
  })
  const [sortOrder, setSortOrder] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("beads-sort-order") || "priority"
    }
    return "priority"
  })
  const [selectedIssue, setSelectedIssue] = useState<BeadIssue | null>(null)
  const [collapsedBeads, setCollapsedBeads] = useState<Set<string>>(new Set())

  // Pagination state
  const [allIssues, setAllIssues] = useState<BeadIssue[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  // Search state: URL param is source of truth, local state for input
  const searchQuery = searchParams.get("q") || ""
  const [searchInput, setSearchInput] = useState(searchQuery)
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Sync search input with URL param when URL changes externally
  useEffect(() => {
    setSearchInput(searchQuery)
  }, [searchQuery])

  // Debounced search: update URL after delay
  const handleSearchChange = useCallback((value: string) => {
    setSearchInput(value)
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    debounceTimerRef.current = setTimeout(() => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (value.trim()) {
          next.set("q", value.trim())
        } else {
          next.delete("q")
        }
        return next
      }, { replace: true })
    }, DEBOUNCE_MS)
  }, [setSearchParams])

  // Clear search
  const clearSearch = useCallback(() => {
    setSearchInput("")
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete("q")
      return next
    }, { replace: true })
  }, [setSearchParams])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current)
      }
    }
  }, [])

  // Persist view preferences to localStorage
  useEffect(() => {
    localStorage.setItem("beads-view-mode", viewMode)
  }, [viewMode])

  useEffect(() => {
    localStorage.setItem("beads-sort-order", sortOrder)
  }, [sortOrder])

  // All issues query using global filters
  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery({
    queryKey: [
      "beads-issues-all",
      repoFilter,
      createdByFilter,
      statusFilter,
      typeFilter,
      searchQuery,
    ],
    queryFn: () =>
      api.listBeadIssues({
        repo: repoFilter || undefined,
        createdBy: createdByFilter || undefined,
        status: statusFilter === "active" ? "open,in_progress" : statusFilter || undefined,
        type: typeFilter === "all" ? undefined : typeFilter,
        q: searchQuery || undefined,
        limit: 50,
      }),
    refetchInterval: 30000,
  })

  // Sync query data to local state (fixes navigation cache bug + enables pagination)
  useEffect(() => {
    if (data) {
      setAllIssues(data.issues)
      setNextCursor(data.next_cursor)
      setHasMore(data.has_more)
    }
  }, [data])

  // Load more issues
  const handleLoadMore = useCallback(async () => {
    if (!nextCursor || isLoadingMore) return

    setIsLoadingMore(true)
    try {
      const result = await api.listBeadIssues({
        repo: repoFilter || undefined,
        createdBy: createdByFilter || undefined,
        status: statusFilter === "active" ? "open,in_progress" : statusFilter || undefined,
        type: typeFilter === "all" ? undefined : typeFilter,
        q: searchQuery || undefined,
        limit: 50,
        cursor: nextCursor,
      })
      setAllIssues(prev => [...prev, ...result.issues])
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
    } finally {
      setIsLoadingMore(false)
    }
  }, [nextCursor, isLoadingMore, api, repoFilter, createdByFilter, statusFilter, typeFilter, searchQuery])

  const toggleCollapse = useCallback((beadId: string) => {
    setCollapsedBeads(prev => {
      const next = new Set(prev)
      if (next.has(beadId)) {
        next.delete(beadId)
      } else {
        next.add(beadId)
      }
      return next
    })
  }, [])

  const collapseAll = useCallback(() => {
    if (allIssues.length === 0) return
    const allParentIds = new Set<string>()
    const beadIds = new Set(allIssues.map(i => i.bead_id))
    for (const issue of allIssues) {
      const parentBeadId = issue.parent_id?.bead_id
      if (parentBeadId && beadIds.has(parentBeadId)) {
        allParentIds.add(parentBeadId)
      }
    }
    setCollapsedBeads(allParentIds)
  }, [allIssues])

  const expandAll = useCallback(() => {
    setCollapsedBeads(new Set())
  }, [])

  // Get sort comparator based on sortOrder
  const getSortComparator = useCallback((order: string) => {
    return (a: BeadIssue, b: BeadIssue): number => {
      if (order === "recent") {
        const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0
        const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0
        return dateB - dateA
      }
      if (order === "oldest") {
        const dateA = a.updated_at ? new Date(a.updated_at).getTime() : 0
        const dateB = b.updated_at ? new Date(b.updated_at).getTime() : 0
        return dateA - dateB
      }
      // Default: priority (lower = higher priority)
      return a.priority - b.priority
    }
  }, [])

  // Sort and group issues based on viewMode and sortOrder
  const sortedIssues = useMemo((): SortedIssue[] => {
    if (allIssues.length === 0) return []

    const issues = [...allIssues]
    const comparator = getSortComparator(sortOrder)

    if (viewMode === "flat") {
      return issues
        .sort(comparator)
        .map(i => ({ ...i, _indentLevel: 0, _hasChildren: false }))
    }

    // Tree view: build hierarchy using parent_id
    const beadIds = new Set(issues.map(i => i.bead_id))

    // Build children map: parent_bead_id -> children
    const childrenMap = new Map<string, BeadIssue[]>()
    for (const issue of issues) {
      const parentBeadId = issue.parent_id?.bead_id
      if (parentBeadId && beadIds.has(parentBeadId)) {
        if (!childrenMap.has(parentBeadId)) {
          childrenMap.set(parentBeadId, [])
        }
        childrenMap.get(parentBeadId)!.push(issue)
      }
    }

    // Find root beads (no parent_id or parent not in current set)
    const roots = issues.filter(i => {
      const parentBeadId = i.parent_id?.bead_id
      return !parentBeadId || !beadIds.has(parentBeadId)
    })

    // Sort roots using the selected sort order
    roots.sort(comparator)

    // Build flat list with indentation levels and children info
    const result: Array<BeadIssue & { _indentLevel: number; _hasChildren: boolean; _parentId?: string }> = []
    const visited = new Set<string>()

    const addWithChildren = (issue: BeadIssue, level: number, parentId?: string) => {
      if (visited.has(issue.bead_id)) return
      visited.add(issue.bead_id)
      const children = childrenMap.get(issue.bead_id) || []
      result.push({ ...issue, _indentLevel: level, _hasChildren: children.length > 0, _parentId: parentId })

      // Sort children using the selected sort order
      children.sort(comparator)
      for (const child of children) {
        addWithChildren(child, level + 1, issue.bead_id)
      }
    }

    for (const root of roots) {
      addWithChildren(root, 0)
    }

    // Add any orphaned beads (in case of circular dependencies)
    for (const issue of issues) {
      if (!visited.has(issue.bead_id)) {
        result.push({ ...issue, _indentLevel: 0, _hasChildren: false })
      }
    }

    return result
  }, [allIssues, viewMode, sortOrder, getSortComparator])

  // Filter out collapsed children
  const visibleIssues = useMemo((): SortedIssue[] => {
    if (viewMode !== "tree" || collapsedBeads.size === 0) {
      return sortedIssues
    }

    // Check if any ancestor is collapsed
    const findCollapsedAncestor = (issue: SortedIssue): boolean => {
      if (!issue._parentId) return false
      if (collapsedBeads.has(issue._parentId)) return true
      const parent = sortedIssues.find(i => i.bead_id === issue._parentId)
      return parent ? findCollapsedAncestor(parent) : false
    }

    return sortedIssues.filter(issue => !findCollapsedAncestor(issue))
  }, [sortedIssues, viewMode, collapsedBeads])

  // Build scope label
  const scopeLabel = repoFilter
    ? `Repo: ${repoFilter}`
    : "All workspaces"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Beads</h1>
          <p className="text-sm text-muted-foreground">{scopeLabel}</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search..."
              value={searchInput}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="pl-9 pr-8 h-9"
              aria-label="Search beads by ID or title"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                aria-label="Clear search"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
          <Select value={viewMode} onValueChange={setViewMode}>
            <SelectTrigger className="w-[90px] h-9">
              <SelectValue placeholder="View" />
            </SelectTrigger>
            <SelectContent>
              {viewModes.map((mode) => (
                <SelectItem key={mode.value} value={mode.value}>
                  {mode.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {viewMode === "tree" && (
            <Button
              variant="outline"
              size="sm"
              onClick={collapsedBeads.size > 0 ? expandAll : collapseAll}
              title={collapsedBeads.size > 0 ? "Expand all" : "Collapse all"}
            >
              <ChevronsUpDown className="h-4 w-4" />
            </Button>
          )}
          <Select value={sortOrder} onValueChange={setSortOrder}>
            <SelectTrigger className="w-[100px] h-9">
              <SelectValue placeholder="Sort" />
            </SelectTrigger>
            <SelectContent>
              {sortOrders.map((order) => (
                <SelectItem key={order.value} value={order.value}>
                  {order.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={typeFilter} onValueChange={setTypeFilter}>
            <SelectTrigger className="w-[120px] h-9">
              <SelectValue placeholder="All types" />
            </SelectTrigger>
            <SelectContent>
              {issueTypes.map((type) => (
                <SelectItem key={type.value} value={type.value}>
                  {type.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
          <TabsTrigger value="active">Active</TabsTrigger>
          <TabsTrigger value="closed">Closed</TabsTrigger>
          <TabsTrigger value="">All</TabsTrigger>
        </TabsList>

        <TabsContent value={statusFilter} className="mt-4">
          {/* Error State */}
          {error && (
            <Card className="border-destructive">
              <CardContent className="p-4">
                <p className="text-sm text-destructive">
                  Failed to load beads: {(error as Error).message}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Loading State */}
          {isLoading && !data && (
            <div className="text-center py-12 text-muted-foreground">
              Loading beads...
            </div>
          )}

          {/* Empty State */}
          {visibleIssues.length === 0 && !isLoading && (
            <Card>
              <CardContent className="p-8 text-center">
                <ListTodo className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  {searchQuery
                    ? `No beads matching "${searchQuery}"`
                    : statusFilter === "active"
                    ? "No active beads"
                    : statusFilter === "closed"
                    ? "No closed beads"
                    : "No beads found"}
                </p>
                {searchQuery && (
                  <Button
                    variant="link"
                    className="mt-2"
                    onClick={clearSearch}
                  >
                    Clear search
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          {/* Issues List */}
          {visibleIssues.length > 0 && (
            <div className="grid gap-2">
              {visibleIssues.map((issue) => (
                <div
                  key={issue.bead_id}
                  style={{ marginLeft: (issue._indentLevel || 0) * 20 }}
                >
                  <IssueCard
                    issue={issue}
                    onSelect={setSelectedIssue}
                    onSelectCreator={(creator) => setCreatedByFilter(creator)}
                    indentLevel={issue._indentLevel || 0}
                    hasChildren={issue._hasChildren || false}
                    isCollapsed={collapsedBeads.has(issue.bead_id)}
                    onToggleCollapse={() => toggleCollapse(issue.bead_id)}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          <Pagination
            onLoadMore={handleLoadMore}
            hasMore={hasMore}
            isLoading={isLoadingMore}
            itemCount={allIssues.length}
          />
        </TabsContent>
      </Tabs>

      {/* Issue Detail Sheet */}
      <IssueDetailSheet
        issue={selectedIssue}
        onClose={() => setSelectedIssue(null)}
        onNavigate={(beadId) => {
          const issue = allIssues.find((i) => i.bead_id === beadId)
          if (issue) setSelectedIssue(issue)
        }}
      />
    </div>
  )
}
