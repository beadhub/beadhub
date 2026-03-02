#!/usr/bin/env bash
# oauth-refresh.sh — Sidecar script that refreshes Claude OAuth tokens before expiry.
#
# Runs in a loop, checking the credentials file every CHECK_INTERVAL seconds.
# When the access token is within REFRESH_BEFORE seconds of expiry, it calls
# the Anthropic OAuth token endpoint to get fresh tokens and writes them back.
#
# Environment:
#   CREDENTIALS_FILE  — path to .credentials.json (default: /home/node/.claude/.credentials.json)
#   CHECK_INTERVAL    — seconds between checks (default: 300 = 5 minutes)
#   REFRESH_BEFORE    — seconds before expiry to trigger refresh (default: 1800 = 30 minutes)
#
# The refresh token is rotated on each use (standard OAuth rotation).
# The script writes atomically via tmp file + mv to avoid partial reads.

set -euo pipefail

CREDENTIALS_FILE="${CREDENTIALS_FILE:-/home/node/.claude/.credentials.json}"
CHECK_INTERVAL="${CHECK_INTERVAL:-300}"
REFRESH_BEFORE="${REFRESH_BEFORE:-1800}"

TOKEN_URL="https://platform.claude.com/v1/oauth/token"
CLIENT_ID="9d1c250a-e61b-44d9-88ed-5944d1962f5e"

log() { echo "[oauth-refresh] $(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }

# Wait for the credentials file to appear (init container writes it)
wait_for_credentials() {
  local attempts=0
  while [ ! -f "$CREDENTIALS_FILE" ]; do
    attempts=$((attempts + 1))
    if [ $attempts -ge 60 ]; then
      log "ERROR: Credentials file not found after 5 minutes: $CREDENTIALS_FILE"
      exit 1
    fi
    sleep 5
  done
  log "Credentials file found: $CREDENTIALS_FILE"
}

# Read the current tokens from credentials file
read_credentials() {
  jq -r '.claudeAiOauth | "\(.accessToken)\n\(.refreshToken)\n\(.expiresAt // "")"' "$CREDENTIALS_FILE"
}

# Check if the token needs refreshing
needs_refresh() {
  local expires_at="$1"

  if [ -z "$expires_at" ] || [ "$expires_at" = "null" ]; then
    log "No expiresAt found — refreshing"
    return 0
  fi

  # expiresAt can be epoch ms or ISO string
  local expires_epoch
  if echo "$expires_at" | grep -qP '^\d+$'; then
    # Epoch milliseconds
    expires_epoch=$((expires_at / 1000))
  else
    # ISO string
    expires_epoch=$(date -d "$expires_at" +%s 2>/dev/null || echo 0)
  fi

  local now
  now=$(date +%s)
  local remaining=$((expires_epoch - now))

  if [ "$remaining" -le "$REFRESH_BEFORE" ]; then
    log "Token expires in ${remaining}s (threshold: ${REFRESH_BEFORE}s) — refreshing"
    return 0
  else
    log "Token valid for ${remaining}s — no refresh needed"
    return 1
  fi
}

# Refresh the OAuth token
do_refresh() {
  local refresh_token="$1"

  local response
  response=$(curl -s -L -X POST "$TOKEN_URL" \
    -H "Content-Type: application/json" \
    -d "{\"grant_type\": \"refresh_token\", \"refresh_token\": \"$refresh_token\", \"client_id\": \"$CLIENT_ID\"}" \
    --max-time 30)

  local error
  error=$(echo "$response" | jq -r '.error // empty')
  if [ -n "$error" ]; then
    local desc
    desc=$(echo "$response" | jq -r '.error_description // "unknown"')
    log "ERROR: Refresh failed: $error — $desc"
    return 1
  fi

  local new_at new_rt expires_in
  new_at=$(echo "$response" | jq -r '.access_token')
  new_rt=$(echo "$response" | jq -r '.refresh_token // empty')
  expires_in=$(echo "$response" | jq -r '.expires_in')

  if [ -z "$new_at" ] || [ "$new_at" = "null" ]; then
    log "ERROR: No access_token in response"
    return 1
  fi

  # Use rotated refresh token, or keep the old one if not returned
  if [ -z "$new_rt" ] || [ "$new_rt" = "null" ]; then
    new_rt="$refresh_token"
  fi

  # Calculate expiresAt as epoch milliseconds (Claude Code format)
  local now_ms
  now_ms=$(( $(date +%s) * 1000 + expires_in * 1000 ))

  # Atomic write: update credentials file
  local tmp_file="${CREDENTIALS_FILE}.tmp"
  jq --arg at "$new_at" --arg rt "$new_rt" --argjson ea "$now_ms" \
    '.claudeAiOauth.accessToken = $at | .claudeAiOauth.refreshToken = $rt | .claudeAiOauth.expiresAt = $ea' \
    "$CREDENTIALS_FILE" > "$tmp_file" && mv "$tmp_file" "$CREDENTIALS_FILE"

  log "Refreshed — new token valid for ${expires_in}s ($(( expires_in / 3600 ))h)"
  return 0
}

# Main loop
main() {
  log "Starting OAuth refresh sidecar"
  log "  Credentials: $CREDENTIALS_FILE"
  log "  Check interval: ${CHECK_INTERVAL}s"
  log "  Refresh before: ${REFRESH_BEFORE}s"

  wait_for_credentials

  while true; do
    # Read current state
    local creds
    creds=$(read_credentials 2>/dev/null || echo "")
    if [ -z "$creds" ]; then
      log "WARNING: Could not read credentials, retrying..."
      sleep "$CHECK_INTERVAL"
      continue
    fi

    local access_token refresh_token expires_at
    access_token=$(echo "$creds" | sed -n '1p')
    refresh_token=$(echo "$creds" | sed -n '2p')
    expires_at=$(echo "$creds" | sed -n '3p')

    if [ -z "$refresh_token" ] || [ "$refresh_token" = "null" ]; then
      log "WARNING: No refresh token found, cannot refresh"
      sleep "$CHECK_INTERVAL"
      continue
    fi

    if needs_refresh "$expires_at"; then
      if do_refresh "$refresh_token"; then
        log "Token refresh successful"
      else
        log "WARNING: Token refresh failed, will retry in ${CHECK_INTERVAL}s"
      fi
    fi

    sleep "$CHECK_INTERVAL"
  done
}

main
