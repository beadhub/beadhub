import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { formatRelativeTime, formatEventDescription } from "@beadhub/dashboard"
import type { SSEEvent } from "@beadhub/dashboard"

describe("formatRelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-02-19T12:00:00Z"))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("returns 'just now' for timestamps less than 60 seconds ago", () => {
    expect(formatRelativeTime("2026-02-19T11:59:30Z")).toBe("just now")
  })

  it("returns minutes ago for timestamps less than 1 hour ago", () => {
    expect(formatRelativeTime("2026-02-19T11:55:00Z")).toBe("5m ago")
  })

  it("returns hours ago for timestamps less than 24 hours ago", () => {
    expect(formatRelativeTime("2026-02-19T09:00:00Z")).toBe("3h ago")
  })

  it("returns days ago for timestamps less than 7 days ago", () => {
    expect(formatRelativeTime("2026-02-17T12:00:00Z")).toBe("2d ago")
  })

  it("returns locale date string for timestamps older than 7 days", () => {
    const result = formatRelativeTime("2026-02-01T12:00:00Z")
    // toLocaleDateString format varies by locale, just check it's not a relative string
    expect(result).not.toContain("ago")
    expect(result).not.toBe("unknown")
  })

  it("returns 'unknown' for invalid date strings", () => {
    expect(formatRelativeTime("not-a-date")).toBe("unknown")
  })
})

describe("formatEventDescription", () => {
  function makeEvent(overrides: Partial<SSEEvent> & { type: string }): SSEEvent {
    return {
      timestamp: "2026-02-19T12:00:00Z",
      workspace_id: "ws-1",
      ...overrides,
    }
  }

  it("formats bead.claimed events", () => {
    const event = makeEvent({
      type: "bead.claimed",
      alias: "alice",
      bead_id: "beadhub-f3vd",
      title: "Backend: Expose human_name in status endpoint",
    })
    expect(formatEventDescription(event)).toBe(
      "alice claimed beadhub-f3vd: Backend: Expose human_name in status endpoint"
    )
  })

  it("formats bead.unclaimed events", () => {
    const event = makeEvent({
      type: "bead.unclaimed",
      alias: "alice",
      bead_id: "beadhub-f3vd",
      title: "Short title",
    })
    expect(formatEventDescription(event)).toBe(
      "alice released beadhub-f3vd: Short title"
    )
  })

  it("formats bead.status_changed with known status verbs", () => {
    const event = makeEvent({
      type: "bead.status_changed",
      alias: "alice",
      bead_id: "beadhub-f3vd",
      new_status: "closed",
      title: "Backend: Expose human_name",
    })
    expect(formatEventDescription(event)).toBe(
      "alice closed beadhub-f3vd: Backend: Expose human_name"
    )
  })

  it("maps in_progress to 'started'", () => {
    const event = makeEvent({
      type: "bead.status_changed",
      alias: "alice",
      bead_id: "beadhub-f3vd",
      new_status: "in_progress",
    })
    expect(formatEventDescription(event)).toBe(
      "alice started beadhub-f3vd"
    )
  })

  it("maps open to 'reopened'", () => {
    const event = makeEvent({
      type: "bead.status_changed",
      alias: "alice",
      bead_id: "beadhub-f3vd",
      new_status: "open",
    })
    expect(formatEventDescription(event)).toBe(
      "alice reopened beadhub-f3vd"
    )
  })

  it("formats message.delivered events", () => {
    const event = makeEvent({
      type: "message.delivered",
      from_alias: "alice",
      to_alias: "bob",
      subject: "API design question",
    })
    expect(formatEventDescription(event)).toBe(
      "alice \u2192 bob: API design question"
    )
  })

  it("formats message.acknowledged events", () => {
    // Backend MessageAcknowledgedEvent does not include alias;
    // if it's ever added, the reader name will appear automatically.
    const event = makeEvent({
      type: "message.acknowledged",
      from_alias: "alice",
      subject: "API design question",
    })
    expect(formatEventDescription(event)).toBe(
      "read mail from alice: API design question"
    )
  })

  it("formats chat.message_sent events", () => {
    const event = makeEvent({
      type: "chat.message_sent",
      from_alias: "alice",
      to_aliases: ["bob"],
      preview: "looks good to me",
    })
    expect(formatEventDescription(event)).toBe(
      "alice \u2192 bob: looks good to me"
    )
  })

  it("formats chat.message_sent with multiple recipients", () => {
    const event = makeEvent({
      type: "chat.message_sent",
      from_alias: "alice",
      to_aliases: ["bob", "charlie"],
      preview: "looks good to me",
    })
    expect(formatEventDescription(event)).toBe(
      "alice \u2192 bob, charlie: looks good to me"
    )
  })

  it("formats escalation.created events", () => {
    const event = makeEvent({
      type: "escalation.created",
      alias: "alice",
      subject: "Need help with merge conflict",
    })
    expect(formatEventDescription(event)).toBe(
      "alice escalated: Need help with merge conflict"
    )
  })

  it("formats escalation.responded events", () => {
    const event = makeEvent({
      type: "escalation.responded",
      escalation_id: "abc123",
    })
    expect(formatEventDescription(event)).toBe(
      "escalation responded"
    )
  })

  it("formats escalation.responded with response preview", () => {
    const event = makeEvent({
      type: "escalation.responded",
      escalation_id: "abc123",
      response: "Fixed by rebasing onto main",
    })
    expect(formatEventDescription(event)).toBe(
      "escalation responded: Fixed by rebasing onto main"
    )
  })

  it("formats reservation.acquired events", () => {
    const event = makeEvent({
      type: "reservation.acquired",
      alias: "alice",
      paths: ["src/api.ts", "src/lib.ts"],
    })
    expect(formatEventDescription(event)).toBe(
      "alice locked src/api.ts, src/lib.ts"
    )
  })

  it("formats reservation.acquired with many paths (shows first 2 + count)", () => {
    const event = makeEvent({
      type: "reservation.acquired",
      alias: "alice",
      paths: ["src/a.ts", "src/b.ts", "src/c.ts", "src/d.ts"],
    })
    expect(formatEventDescription(event)).toBe(
      "alice locked src/a.ts, src/b.ts +2 more"
    )
  })

  it("formats reservation.released events", () => {
    const event = makeEvent({
      type: "reservation.released",
      alias: "alice",
      paths: ["src/api.ts"],
    })
    expect(formatEventDescription(event)).toBe(
      "alice unlocked src/api.ts"
    )
  })

  it("formats reservation.renewed events", () => {
    const event = makeEvent({
      type: "reservation.renewed",
      alias: "alice",
      paths: ["src/api.ts"],
    })
    expect(formatEventDescription(event)).toBe(
      "alice renewed lock on src/api.ts"
    )
  })

  it("falls back to raw event type for unknown events", () => {
    const event = makeEvent({ type: "workspace.connected" })
    expect(formatEventDescription(event)).toBe("workspace.connected")
  })

  it("truncates title at ~50 chars with ellipsis", () => {
    const longTitle = "A".repeat(60)
    const event = makeEvent({
      type: "bead.claimed",
      alias: "alice",
      bead_id: "beadhub-f3vd",
      title: longTitle,
    })
    const result = formatEventDescription(event)
    // "alice claimed beadhub-f3vd: " + truncated title
    expect(result).toContain("...")
    // The title portion should be ~50 chars
    const titlePart = result.split(": ").slice(1).join(": ")
    expect(titlePart.length).toBeLessThanOrEqual(53) // 50 + "..."
  })

  it("handles bead events without title", () => {
    const event = makeEvent({
      type: "bead.claimed",
      alias: "alice",
      bead_id: "beadhub-f3vd",
    })
    expect(formatEventDescription(event)).toBe(
      "alice claimed beadhub-f3vd"
    )
  })

  it("handles message events without subject", () => {
    const event = makeEvent({
      type: "message.delivered",
      from_alias: "alice",
      to_alias: "bob",
    })
    expect(formatEventDescription(event)).toBe("alice \u2192 bob")
  })
})
