#!/usr/bin/env bash
# discord-status.sh — PostToolUse hook for ordis
#
# Posts a "thinking" indicator to #ordis Discord channel via webhook.
# Heavy rate-limiting (30s) to avoid flooding — just signals "I'm still working".
#
# Claude Code PostToolUse hooks receive JSON via stdin with fields like:
#   { "hook_type": "PostToolUse", "tool_name": "Bash", "tool_input": {...}, ... }
#
# Required env var:
#   DISCORD_ORDIS_WEBHOOK_URL — Discord webhook for #ordis channel

# Bail if no webhook configured
[ -z "${DISCORD_ORDIS_WEBHOOK_URL:-}" ] && { cat >/dev/null; exit 0; }

# Rate limit: skip if last post was <30s ago
LOCKFILE="/tmp/discord-status-last"
NOW=$(date +%s)
LAST=$(cat "$LOCKFILE" 2>/dev/null || echo 0)
if [ $((NOW - LAST)) -lt 30 ]; then
  cat >/dev/null
  exit 0
fi
echo "$NOW" > "$LOCKFILE"

# Drain stdin (required even if we don't use it)
cat >/dev/null

# Post to Discord (fire-and-forget, never fail the hook)
curl -sf -H "Content-Type: application/json" \
  -d '{"username":"🎯 ordis","content":"💭 *thinking...*"}' \
  "$DISCORD_ORDIS_WEBHOOK_URL" >/dev/null 2>&1 || true
