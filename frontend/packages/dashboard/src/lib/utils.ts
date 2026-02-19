import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

import type { SSEEvent } from "../hooks/useSSE"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) return "unknown"
  const now = new Date()
  const diffMs = Math.max(0, now.getTime() - date.getTime())
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return "just now"
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 7) return `${diffDay}d ago`
  return date.toLocaleDateString()
}

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text
  return text.slice(0, maxLen) + "..."
}

function formatPaths(paths: string[]): string {
  if (paths.length <= 2) return paths.join(", ")
  return `${paths[0]}, ${paths[1]} +${paths.length - 2} more`
}

const STATUS_VERBS: Record<string, string> = {
  closed: "closed",
  open: "reopened",
  in_progress: "started",
}

export function formatEventDescription(event: SSEEvent): string {
  const alias = event.alias as string | undefined
  const beadId = event.bead_id as string | undefined
  const title = event.title as string | undefined
  const subject = event.subject as string | undefined
  const fromAlias = event.from_alias as string | undefined
  const toAlias = event.to_alias as string | undefined
  const toAliases = event.to_aliases as string[] | undefined
  const preview = event.preview as string | undefined
  const paths = event.paths as string[] | undefined
  const response = event.response as string | undefined
  const newStatus = event.new_status as string | undefined

  const beadSuffix = title ? `: ${truncate(title, 50)}` : ""

  switch (event.type) {
    case "bead.claimed":
      return `${alias} claimed ${beadId}${beadSuffix}`

    case "bead.unclaimed":
      return `${alias} released ${beadId}${beadSuffix}`

    case "bead.status_changed": {
      const verb = STATUS_VERBS[newStatus ?? ""] ?? newStatus
      return `${alias} ${verb} ${beadId}${beadSuffix}`
    }

    case "message.delivered": {
      const suffix = subject ? `: ${truncate(subject, 50)}` : ""
      return `${fromAlias} \u2192 ${toAlias}${suffix}`
    }

    case "message.acknowledged": {
      const suffix = subject ? `: ${truncate(subject, 50)}` : ""
      // alias is the reader (event fires on the reader's workspace)
      const reader = alias ? `${alias} ` : ""
      return `${reader}read mail from ${fromAlias}${suffix}`
    }

    case "chat.message_sent": {
      const recipients = toAliases?.join(", ") ?? ""
      const suffix = preview ? `: ${truncate(preview, 50)}` : ""
      return `${fromAlias} \u2192 ${recipients}${suffix}`
    }

    case "escalation.created":
      return `${alias} escalated: ${truncate(subject ?? "", 50)}`

    case "escalation.responded": {
      const suffix = response ? `: ${truncate(response, 50)}` : ""
      return `escalation responded${suffix}`
    }

    case "reservation.acquired":
      return `${alias} locked ${formatPaths(paths ?? [])}`

    case "reservation.released":
      return `${alias} unlocked ${formatPaths(paths ?? [])}`

    case "reservation.renewed":
      return `${alias} renewed lock on ${formatPaths(paths ?? [])}`

    default:
      return event.type
  }
}
