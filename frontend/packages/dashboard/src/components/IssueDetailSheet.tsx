import { useState, useRef, useEffect } from "react"
import { useQuery } from "@tanstack/react-query"
import { useApi } from "../hooks/useApi"
import { AlertTriangle, Calendar, Clock, GitBranch, Tag, User, Copy, Check } from "lucide-react"
import { Markdown } from "./Markdown"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "./ui/sheet"
import { Badge } from "./ui/badge"
import { Separator } from "./ui/separator"
import { type ApiClient, type BeadIssue } from "../lib/api"
import { cn, formatRelativeTime } from "../lib/utils"

const statusStyles: Record<string, { dot: string; label: string }> = {
  open: { dot: "bg-green-500", label: "Open" },
  in_progress: { dot: "bg-blue-500", label: "In Progress" },
  closed: { dot: "bg-purple-500", label: "Closed" },
}

const priorityStyles: Record<number, { text: string; border: string }> = {
  0: { text: "text-red-400", border: "border-red-400/50" },
  1: { text: "text-amber-500", border: "border-amber-500/50" },
  2: { text: "text-foreground", border: "border-border" },
  3: { text: "text-muted-foreground", border: "border-border" },
  4: { text: "text-muted-foreground/60", border: "border-border" },
}

const typeIcons: Record<string, string> = {
  bug: "text-red-400",
  feature: "text-green-400",
  task: "text-blue-400",
  epic: "text-purple-400",
  chore: "text-muted-foreground",
}

interface IssueDetailSheetProps {
  issue: BeadIssue | null
  onClose: () => void
  onNavigate: (beadId: string) => void
}

export function IssueDetailSheet({
  issue: initialIssue,
  onClose,
  onNavigate,
}: IssueDetailSheetProps) {
  const [copied, setCopied] = useState(false)
  const copyTimeoutRef = useRef<number | null>(null)
  const api = useApi<ApiClient>()
  const beadId = initialIssue?.bead_id

  const { data: fetchedIssue, isLoading } = useQuery({
    queryKey: ["bead-issue", beadId],
    queryFn: () => api.getBeadIssue(beadId!),
    enabled: !!beadId,
  })

  // Merge fetched issue (has description) with initial issue (has timestamps from list)
  const issue = fetchedIssue
    ? {
        ...fetchedIssue,
        created_at: fetchedIssue.created_at ?? initialIssue?.created_at,
        updated_at: fetchedIssue.updated_at ?? initialIssue?.updated_at,
      }
    : initialIssue

  const status = issue ? statusStyles[issue.status] : null
  const priority = issue ? priorityStyles[issue.priority] : null

  useEffect(() => {
    return () => {
      if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
    }
  }, [])

  const handleCopyId = async () => {
    if (issue?.bead_id) {
      try {
        await navigator.clipboard.writeText(issue.bead_id)
        setCopied(true)
        if (copyTimeoutRef.current) clearTimeout(copyTimeoutRef.current)
        copyTimeoutRef.current = window.setTimeout(() => setCopied(false), 1500)
      } catch (err) {
        console.error("Failed to copy bead ID:", err)
      }
    }
  }

  return (
    <Sheet open={initialIssue !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex flex-col overflow-hidden p-0">
        {/* Header */}
        <div className="border-b bg-card/50 px-6 py-5">
          <SheetHeader className="space-y-3">
            {/* Status & ID row */}
            <div className="flex items-center gap-3">
              {status && (
                <div className="flex items-center gap-2">
                  <div className={cn("h-2.5 w-2.5 rounded-full", status.dot)} />
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    {status.label}
                  </span>
                </div>
              )}
              <Badge
                variant="outline"
                className="font-mono text-xs tracking-tight cursor-pointer hover:bg-accent hover:text-accent-foreground group/badge"
                onClick={handleCopyId}
                title="Click to copy bead ID"
              >
                {issue?.bead_id}
                {copied ? (
                  <Check className="h-3 w-3 ml-1.5 text-green-500" />
                ) : (
                  <Copy className="h-3 w-3 ml-1.5 opacity-40 group-hover/badge:opacity-100" />
                )}
              </Badge>
              {issue && priority && (
                <Badge
                  variant="outline"
                  className={cn("text-xs", priority.text, priority.border)}
                >
                  P{issue.priority}
                </Badge>
              )}
            </div>

            {/* Title */}
            {issue && (
              <SheetTitle className="text-xl leading-tight pr-8">
                {issue.title}
              </SheetTitle>
            )}

            {/* Meta row */}
            {issue && (
              <SheetDescription className="flex items-center gap-2 text-xs">
                <span className={cn("font-medium", typeIcons[issue.type] || "text-muted-foreground")}>
                  {issue.type}
                </span>
                <span className="text-muted-foreground/50">in</span>
                <span className="font-medium font-mono">{issue.repo}</span>
                <span className="text-muted-foreground/50">/</span>
                <span className="flex items-center gap-1 font-mono">
                  <GitBranch className="h-3 w-3" />
                  {issue.branch}
                </span>
              </SheetDescription>
            )}
          </SheetHeader>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">
          {issue && (
            <div className="p-6 space-y-6">
              {/* Description */}
              <section>
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">
                  Description
                </h3>
                {isLoading ? (
                  <div className="space-y-2">
                    <div className="h-3 w-full animate-pulse rounded bg-muted" />
                    <div className="h-3 w-5/6 animate-pulse rounded bg-muted" />
                    <div className="h-3 w-4/6 animate-pulse rounded bg-muted" />
                  </div>
                ) : issue.description ? (
                  <div className="rounded-lg border bg-muted/30 p-4">
                    <Markdown className="text-sm leading-relaxed text-foreground/90">
                      {issue.description}
                    </Markdown>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    No description provided
                  </p>
                )}
              </section>

              <Separator />

              {/* Created by */}
              {issue.created_by && (
                <section>
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">
                    Created by
                  </h3>
                  <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-accent flex items-center justify-center">
                      <User className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                    <span className="text-sm font-medium">{issue.created_by}</span>
                  </div>
                </section>
              )}

              {issue.created_by && <Separator />}

              {/* Assignee */}
              <section>
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3">
                  Assignee
                </h3>
                {issue.assignee ? (
                  <div className="flex items-center gap-2">
                    <div className="h-6 w-6 rounded-full bg-accent flex items-center justify-center">
                      <User className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                    <span className="text-sm font-medium">{issue.assignee}</span>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    Unassigned
                  </p>
                )}
              </section>

              {/* Created */}
              {issue.created_at && (
                <>
                  <Separator />
                  <section>
                    <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3 flex items-center gap-1.5">
                      <Calendar className="h-3 w-3" />
                      Created
                    </h3>
                    <p
                      className="text-sm"
                      title={new Date(issue.created_at).toLocaleString()}
                    >
                      {formatRelativeTime(issue.created_at)}
                    </p>
                  </section>
                </>
              )}

              {/* Last Updated */}
              {issue.updated_at && (
                <>
                  <Separator />
                  <section>
                    <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3 flex items-center gap-1.5">
                      <Clock className="h-3 w-3" />
                      Last Updated
                    </h3>
                    <p
                      className="text-sm"
                      title={new Date(issue.updated_at).toLocaleString()}
                    >
                      {formatRelativeTime(issue.updated_at)}
                    </p>
                  </section>
                </>
              )}

              {/* Labels */}
              {issue.labels && issue.labels.length > 0 && (
                <>
                  <Separator />
                  <section>
                    <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-3 flex items-center gap-1.5">
                      <Tag className="h-3 w-3" />
                      Labels
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {issue.labels.map((label) => (
                        <Badge
                          key={label}
                          variant="secondary"
                          className="text-xs"
                        >
                          {label}
                        </Badge>
                      ))}
                    </div>
                  </section>
                </>
              )}

              {/* Blockers */}
              {issue.blocked_by && issue.blocked_by.length > 0 && (
                <>
                  <Separator />
                  <section>
                    <h3 className="text-xs font-medium text-amber-500 uppercase tracking-wide mb-3 flex items-center gap-1.5">
                      <AlertTriangle className="h-3 w-3" />
                      Blocked by
                    </h3>
                    <div className="space-y-2">
                      {issue.blocked_by.map((blocker) => (
                        <div
                          key={blocker.bead_id}
                          className="flex items-center gap-2 p-2 rounded-md border border-amber-500/20 bg-amber-500/5 hover:bg-amber-500/10 transition-colors cursor-pointer"
                          onClick={() => onNavigate(blocker.bead_id)}
                        >
                          <Badge
                            variant="outline"
                            className="font-mono text-xs border-amber-500/30 text-amber-500 hover:bg-amber-500/20"
                          >
                            {blocker.bead_id}
                          </Badge>
                          <span className="text-xs text-muted-foreground font-mono">
                            {blocker.repo} / {blocker.branch}
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                </>
              )}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
