#!/usr/bin/env bash
set -euo pipefail

# message-watcher.sh — Ordis control-plane message loop
#
# Polls BeadHub for pending chat messages via HTTP API,
# streams claude -p output (stream-json format), posts tool activity
# to a Discord thread, and sends final responses back via the API.
#
# Required env vars:
#   BEADHUB_API               — BeadHub API base URL (e.g., http://beadhub-api)
#   ORDIS_API_KEY             — Ordis's aweb API key (aw_sk_...)
#   DISCORD_ORDIS_WEBHOOK_URL — Discord webhook for #ordis channel
#   CLAUDE_CODE_OAUTH_TOKEN   — Claude Code auth token (from claude setup-token)
#   REDIS_URL                 — Redis URL for thread ID lookups (e.g., redis://redis:6379)
#
# Optional:
#   POLL_INTERVAL — seconds between polls (default: 5)

POLL_INTERVAL="${POLL_INTERVAL:-5}"
FIRST_CALL=true

# Helper: post a message to a Discord thread via webhook
post_to_thread() {
  local thread_id="$1"
  local content="$2"
  if [ -z "$thread_id" ] || [ -z "$content" ]; then return; fi
  curl -sf -X POST -H "Content-Type: application/json" \
    -d "{\"username\":\"🎯 ordis\",\"content\":$(echo "$content" | jq -Rs .),\"thread_id\":\"$thread_id\"}" \
    "$DISCORD_ORDIS_WEBHOOK_URL" >/dev/null 2>&1 || true
}

# Helper: format a tool summary from tool name + input JSON
format_tool_summary() {
  local tool="$1"
  local input="$2"
  case "$tool" in
    Bash|bash)
      local cmd
      cmd=$(echo "$input" | jq -r '.command // ""' 2>/dev/null | head -1 | cut -c1-100)
      echo "🔧 \`$cmd\`"
      ;;
    Read|read)
      local file
      file=$(echo "$input" | jq -r '.file_path // ""' 2>/dev/null | sed 's|.*/||')
      echo "📖 Reading $file"
      ;;
    Write|write)
      local file
      file=$(echo "$input" | jq -r '.file_path // ""' 2>/dev/null | sed 's|.*/||')
      echo "📝 Writing $file"
      ;;
    Edit|edit)
      local file
      file=$(echo "$input" | jq -r '.file_path // ""' 2>/dev/null | sed 's|.*/||')
      echo "✏️ Editing $file"
      ;;
    Grep|grep)
      local pattern
      pattern=$(echo "$input" | jq -r '.pattern // ""' 2>/dev/null | cut -c1-60)
      echo "🔍 Searching: \`$pattern\`"
      ;;
    Glob|glob)
      local pattern
      pattern=$(echo "$input" | jq -r '.pattern // ""' 2>/dev/null | cut -c1-60)
      echo "📂 Finding: \`$pattern\`"
      ;;
    Agent|agent)
      local desc
      desc=$(echo "$input" | jq -r '.description // ""' 2>/dev/null | cut -c1-80)
      echo "🤖 Agent: $desc"
      ;;
    *)
      echo "⚙️ $tool"
      ;;
  esac
}

echo "[message-watcher] Entering message watch loop (poll every ${POLL_INTERVAL}s)..."

while true; do
  # Get pending sessions via BeadHub API (Bearer auth)
  pending_json=$(curl -sf -H "Authorization: Bearer $ORDIS_API_KEY" \
    "$BEADHUB_API/v1/chat/pending" 2>/dev/null || echo "")

  # Filter to sessions where last message is NOT from ordis (skip self)
  actionable=$(echo "$pending_json" | jq -r '[.pending[] | select(.last_from != "ordis")] | length' 2>/dev/null || echo "0")
  if [ "$actionable" -gt 0 ]; then
    echo "[message-watcher] $actionable actionable message(s) detected"

    # Extract fields safely (avoid shell word-splitting on JSON)
    session_id=$(echo "$pending_json" | jq -r '[.pending[] | select(.last_from != "ordis")][0].session_id // ""')
    sender=$(echo "$pending_json" | jq -r '[.pending[] | select(.last_from != "ordis")][0].last_from // "someone"')
    last_msg=$(echo "$pending_json" | jq -r '[.pending[] | select(.last_from != "ordis")][0].last_message // ""')

    if [ -n "$last_msg" ] && [ -n "$session_id" ]; then
      echo "[message-watcher] Processing message from $sender (session: ${session_id:0:8}...)"

      # Look up Discord thread ID from Redis (set by discord-bridge)
      THREAD_ID=$(redis-cli -u "$REDIS_URL" GET "ordis:thread:$session_id" 2>/dev/null || echo "")

      # Build claude args
      CLAUDE_ARGS=(-p "$sender says: $last_msg" --dangerously-skip-permissions --output-format stream-json --verbose)
      if [ "$FIRST_CALL" = true ]; then
        FIRST_CALL=false
      else
        CLAUDE_ARGS+=(--continue)
      fi

      # Stream-parse claude output: post tool activity to Discord thread
      RESPONSE_FILE=$(mktemp)
      current_tool=""
      tool_input_buf=""
      last_post_time=0

      while IFS= read -r line; do
        event_type=$(echo "$line" | jq -r '.event.type // empty' 2>/dev/null)

        case "$event_type" in
          content_block_start)
            block_type=$(echo "$line" | jq -r '.event.content_block.type // empty' 2>/dev/null)
            if [ "$block_type" = "tool_use" ]; then
              current_tool=$(echo "$line" | jq -r '.event.content_block.name // ""' 2>/dev/null)
              tool_input_buf=""
            fi
            ;;

          content_block_delta)
            delta_type=$(echo "$line" | jq -r '.event.delta.type // empty' 2>/dev/null)
            case "$delta_type" in
              input_json_delta)
                partial=$(echo "$line" | jq -r '.event.delta.partial_json // ""' 2>/dev/null)
                tool_input_buf="${tool_input_buf}${partial}"
                ;;
              text_delta)
                echo -n "$(echo "$line" | jq -r '.event.delta.text // ""' 2>/dev/null)" >> "$RESPONSE_FILE"
                ;;
            esac
            ;;

          content_block_stop)
            if [ -n "$current_tool" ] && [ -n "$THREAD_ID" ]; then
              now=$(date +%s)
              if [ $((now - last_post_time)) -ge 2 ]; then
                summary=$(format_tool_summary "$current_tool" "$tool_input_buf")
                post_to_thread "$THREAD_ID" "$summary"
                last_post_time=$now
              fi
            fi
            current_tool=""
            tool_input_buf=""
            ;;

          message_stop)
            if [ -n "$THREAD_ID" ]; then
              post_to_thread "$THREAD_ID" "✅ Done"
            fi
            ;;
        esac
      done < <(claude "${CLAUDE_ARGS[@]}" 2>/dev/null || true)

      # Send final response back via BeadHub chat API
      response=$(cat "$RESPONSE_FILE")
      rm -f "$RESPONSE_FILE"

      if [ -n "$response" ]; then
        escaped_response=$(echo "$response" | jq -Rs .)
        curl -sf -X POST -H "Authorization: Bearer $ORDIS_API_KEY" \
          -H "Content-Type: application/json" \
          -d "{\"body\": $escaped_response}" \
          "$BEADHUB_API/v1/chat/sessions/$session_id/messages" 2>/dev/null || \
          echo "[message-watcher] Warning: failed to send response to session $session_id"
        echo "[message-watcher] Response sent to $sender"
      else
        echo "[message-watcher] Warning: empty response from claude"
      fi
    fi
  fi
  sleep "$POLL_INTERVAL"
done
