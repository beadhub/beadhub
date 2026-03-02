#!/usr/bin/env bash
# discord-status.sh — PostToolUse hook for ordis
#
# Posts tool activity to the #ordis Discord channel via webhook.
# Rate-limited: skips if last post was <5 seconds ago to avoid flooding.
#
# Claude Code PostToolUse hooks receive JSON via stdin with fields like:
#   { "hook_type": "PostToolUse", "tool_name": "Bash", "tool_input": {...}, ... }
#
# Required env var:
#   DISCORD_ORDIS_WEBHOOK_URL — Discord webhook for #ordis channel

# Bail if no webhook configured
[ -z "${DISCORD_ORDIS_WEBHOOK_URL:-}" ] && { cat >/dev/null; exit 0; }

# Rate limit: skip if last post was <5s ago
LOCKFILE="/tmp/discord-status-last"
NOW=$(date +%s)
LAST=$(cat "$LOCKFILE" 2>/dev/null || echo 0)
if [ $((NOW - LAST)) -lt 5 ]; then
  cat >/dev/null
  exit 0
fi
echo "$NOW" > "$LOCKFILE"

# Parse tool name from stdin JSON
INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // "tool"' 2>/dev/null || echo "tool")

# Post to Discord (fire-and-forget, never fail the hook)
curl -sf -H "Content-Type: application/json" \
  -d "{\"username\":\"🎯 ordis\",\"content\":\"🔧 ${TOOL}\"}" \
  "$DISCORD_ORDIS_WEBHOOK_URL" >/dev/null 2>&1 || true
