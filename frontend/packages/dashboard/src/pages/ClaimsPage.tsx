import { useEffect, useState, useCallback, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import { Clock, GitBranch, RefreshCw, User, AlertTriangle, Copy, Check } from "lucide-react"
import { Card, CardContent } from "../components/ui/card"
import { Badge } from "../components/ui/badge"
import { Button } from "../components/ui/button"
import { IssueDetailSheet } from "../components/IssueDetailSheet"
import { Pagination } from "../components/Pagination"
import { type ApiClient, type Claim, type BeadIssue } from "../lib/api"
import { cn, formatRelativeTime } from "../lib/utils"

function ConflictCard({ beadId, claims, onSelect }: {
  beadId: string
  claims: Claim[]
  onSelect: (beadId: string) => void
}) {
  const [copied, setCopied] = useState(false)
  const copyTimeoutRef = useRef<number | null>(null)
  const title = claims[0]?.title

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    }
  }, [])

  const handleCopyId = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(beadId)
      setCopied(true)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = window.setTimeout(() => setCopied(false), 1500)
    } catch (err) {
      console.error("Failed to copy bead ID:", err)
    }
  }

  return (
    <Card className="border-destructive">
      <CardContent className="p-3">
        <div className="flex items-start gap-2 mb-2">
          <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3
                className="text-sm font-medium truncate cursor-pointer hover:text-primary hover:underline"
                onClick={() => onSelect(beadId)}
              >
                {title || beadId}
              </h3>
              <Badge variant="destructive" className="text-xs">
                {claims.length} claimants
              </Badge>
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <Badge
                variant="outline"
                className="font-mono text-xs cursor-pointer hover:bg-accent hover:text-accent-foreground group/badge"
                onClick={handleCopyId}
                title="Click to copy bead ID"
              >
                {beadId}
                {copied ? (
                  <Check className="h-3 w-3 ml-1.5 text-green-500" />
                ) : (
                  <Copy className="h-3 w-3 ml-1.5 opacity-40 group-hover/badge:opacity-100" />
                )}
              </Badge>
            </div>
          </div>
        </div>

        <div className="space-y-1 ml-6">
          {claims.map(claim => (
            <div key={claim.workspace_id}
                 className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 text-muted-foreground">
                <User className="h-3 w-3" />
                <span className="font-medium text-foreground">{claim.alias}</span>
                {claim.human_name && (
                  <span>({claim.human_name})</span>
                )}
              </div>
              <span className="flex items-center gap-1 text-muted-foreground" title={new Date(claim.claimed_at).toLocaleString()}>
                <Clock className="h-3 w-3" />
                {formatRelativeTime(claim.claimed_at)}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function ClaimCard({ claim, onSelect }: {
  claim: Claim
  onSelect: (beadId: string) => void
}) {
  const [copied, setCopied] = useState(false)
  const copyTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    }
  }, [])

  const handleCopyId = async (e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await navigator.clipboard.writeText(claim.bead_id)
      setCopied(true)
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
      copyTimeoutRef.current = window.setTimeout(() => setCopied(false), 1500)
    } catch (err) {
      console.error("Failed to copy bead ID:", err)
    }
  }

  return (
    <Card>
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <GitBranch className="h-4 w-4 shrink-0 text-accent" />
              <h3
                className="text-sm font-medium truncate cursor-pointer hover:text-primary hover:underline"
                onClick={() => onSelect(claim.bead_id)}
              >
                {claim.title || claim.bead_id}
              </h3>
            </div>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <Badge
                variant="outline"
                className="font-mono text-xs cursor-pointer hover:bg-accent hover:text-accent-foreground group/badge"
                onClick={handleCopyId}
                title="Click to copy bead ID"
              >
                {claim.bead_id}
                {copied ? (
                  <Check className="h-3 w-3 ml-1.5 text-green-500" />
                ) : (
                  <Copy className="h-3 w-3 ml-1.5 opacity-40 group-hover/badge:opacity-100" />
                )}
              </Badge>
              <span>·</span>
              <span className="flex items-center gap-1">
                <User className="h-3 w-3" />
                {claim.alias}
              </span>
              {claim.human_name && (
                <>
                  <span>·</span>
                  <span>{claim.human_name}</span>
                </>
              )}
              <span>·</span>
              <span className="flex items-center gap-1" title={new Date(claim.claimed_at).toLocaleString()}>
                <Clock className="h-3 w-3" />
                {formatRelativeTime(claim.claimed_at)}
              </span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function ClaimsPage() {
  const api = useApi<ApiClient>()
  const [selectedIssue, setSelectedIssue] = useState<BeadIssue | null>(null)
  const [allClaims, setAllClaims] = useState<Claim[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  const {
    data,
    isFetching,
    error,
    refetch,
  } = useQuery({
    queryKey: ["claims"],
    queryFn: async () => {
      return await api.listClaims({
        limit: 50,
      })
    },
    refetchInterval: 30000,
  })

  useEffect(() => {
    if (!data) return
    setAllClaims(data.claims)
    setNextCursor(data.next_cursor)
    setHasMore(data.has_more)
  }, [data])

  const displayedClaims = allClaims.length > 0 ? allClaims : (data?.claims ?? [])

  const handleLoadMore = useCallback(async () => {
    if (!nextCursor || isLoadingMore) return

    setIsLoadingMore(true)
    try {
      const result = await api.listClaims({
        limit: 50,
        cursor: nextCursor,
      })
      setAllClaims(prev => [...prev, ...result.claims])
      setNextCursor(result.next_cursor)
      setHasMore(result.has_more)
    } finally {
      setIsLoadingMore(false)
    }
  }, [nextCursor, isLoadingMore])

  // Fetch issue on demand when user clicks a claim
  const handleSelectClaim = async (beadId: string) => {
    try {
      const issue = await api.getBeadIssue(beadId)
      setSelectedIssue(issue)
    } catch (e) {
      console.error("Failed to fetch issue:", e)
    }
  }

  // Group claims by bead_id to identify conflicts
  const claimsByBeadId = new Map<string, Claim[]>()
  for (const claim of displayedClaims) {
    const existing = claimsByBeadId.get(claim.bead_id) ?? []
    existing.push(claim)
    claimsByBeadId.set(claim.bead_id, existing)
  }

  // Separate conflicts (multiple claimants) from single claims
  const conflicts: { beadId: string; claims: Claim[] }[] = []
  const singleClaims: Claim[] = []
  for (const [beadId, beadClaims] of claimsByBeadId) {
    if (beadClaims.length > 1) {
      conflicts.push({ beadId, claims: beadClaims })
    } else {
      singleClaims.push(beadClaims[0])
    }
  }

  const scopeLabel = "All workspaces"

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Claims</h1>
          <p className="text-sm text-muted-foreground">{scopeLabel}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh claims"
          >
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="p-4">
            <p className="text-sm text-destructive">
              Failed to load claims: {(error as Error).message}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Loading State */}
      {isFetching && displayedClaims.length === 0 && (
        <div className="text-center py-12 text-muted-foreground">
          Loading claims...
        </div>
      )}

      {/* Empty State */}
      {conflicts.length === 0 && singleClaims.length === 0 && !isFetching && (
        <Card>
          <CardContent className="p-8 text-center">
            <GitBranch className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
            <p className="text-muted-foreground">
              No active claims
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              Claims are created when a workspace starts working on a bead
            </p>
          </CardContent>
        </Card>
      )}

      {/* Conflicts first */}
      {conflicts.length > 0 && (
        <div className="grid gap-3">
          {conflicts.map(({ beadId, claims: conflictClaims }) => (
            <ConflictCard
              key={beadId}
              beadId={beadId}
              claims={conflictClaims}
              onSelect={handleSelectClaim}
            />
          ))}
        </div>
      )}

      {/* Single claims */}
      {singleClaims.length > 0 && (
        <div className="grid gap-3">
          {singleClaims.map((claim) => (
            <ClaimCard
              key={`${claim.workspace_id}-${claim.bead_id}`}
              claim={claim}
              onSelect={handleSelectClaim}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      <Pagination
        onLoadMore={handleLoadMore}
        hasMore={hasMore}
        isLoading={isLoadingMore}
        itemCount={displayedClaims.length}
      />

      {/* Issue Detail Sheet */}
      <IssueDetailSheet
        issue={selectedIssue}
        onClose={() => setSelectedIssue(null)}
        onNavigate={handleSelectClaim}
      />
    </div>
  )
}
