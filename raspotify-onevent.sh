#!/bin/bash

# Raspotify onevent hook script
# Called by librespot when Spotify events occur.
# Forwards events to the HSG Canvas API.
#
# Librespot 0.8 event flow:
#   track_changed -> NAME, ARTISTS, ALBUM, COVERS, DURATION_MS, TRACK_ID
#   playing       -> TRACK_ID, POSITION_MS
#   paused        -> TRACK_ID, POSITION_MS
#   stopped       -> TRACK_ID

API_URL="http://localhost:80/audio/spotify/event"
LOG_FILE="/tmp/raspotify-events.log"

# Extract LARGEST cover URL (librespot provides 3 sizes, last is biggest)
COVER_URL=""
if [ -n "$COVERS" ]; then
  COVER_URL=$(echo "$COVERS" | tail -n 1)
fi

# Build JSON safely using jq (handles all escaping)
JSON_PAYLOAD=$(jq -n \
  --arg event "${PLAYER_EVENT:-unknown}" \
  --arg track_id "${TRACK_ID}" \
  --arg old_track_id "${OLD_TRACK_ID}" \
  --arg duration_ms "${DURATION_MS}" \
  --arg position_ms "${POSITION_MS}" \
  --arg name "${NAME}" \
  --arg artists "${ARTISTS}" \
  --arg album "${ALBUM}" \
  --arg covers "$COVER_URL" \
  '{
    event: $event,
    track_id: (if $track_id == "" then null else $track_id end),
    old_track_id: (if $old_track_id == "" then null else $old_track_id end),
    duration_ms: (if $duration_ms == "" then null else ($duration_ms | tonumber) end),
    position_ms: (if $position_ms == "" then null else ($position_ms | tonumber) end),
    name: (if $name == "" then null else $name end),
    artists: (if $artists == "" then null else $artists end),
    album: (if $album == "" then null else $album end),
    covers: (if $covers == "" then null else $covers end)
  }')

# Log (best-effort, never block the curl)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] $PLAYER_EVENT: ${NAME:-$TRACK_ID}" >> "$LOG_FILE" 2>/dev/null
# Debug: log COVERS value on track_changed
if [ "$PLAYER_EVENT" = "track_changed" ]; then
  echo "  COVERS=${COVERS:-EMPTY}" >> "$LOG_FILE" 2>/dev/null
fi

# Send event to the API
curl -X POST "$API_URL" \
  -H "Content-Type: application/json" \
  -d "$JSON_PAYLOAD" \
  --max-time 2 \
  --silent \
  --show-error \
  >> "$LOG_FILE" 2>/dev/null

exit 0
