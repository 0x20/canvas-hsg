#!/bin/bash
URL_FILE=/boot/firmware/kiosk-url.txt
DEFAULT_URL="http://canvas.local/canvas/"
URL=$(cat "$URL_FILE" 2>/dev/null | tr -d "[:space:]")
[ -z "$URL" ] && URL="$DEFAULT_URL"

# Wait for URL host to be reachable (max ~60s)
for i in $(seq 1 30); do
  curl -sSf -o /dev/null --max-time 2 "$URL" && break
  sleep 2
done

PREFS="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i "s/\"exited_cleanly\":false/\"exited_cleanly\":true/; s/\"exit_type\":\"Crashed\"/\"exit_type\":\"Normal\"/" "$PREFS"
fi

command -v unclutter >/dev/null && unclutter -idle 0.1 -root &

# Pi 3B+ GPU performance flags. The base flags (kiosk, ozone, etc.) were here
# already; the new additions are for VC IV under labwc/wlroots:
#   --enable-zero-copy           : direct GPU texture upload, skip CPU staging
#   --canvas-oop-rasterization   : out-of-process canvas raster
#   --num-raster-threads=4       : use all 4 cores (was 2 by default)
#   --ignore-gpu-blocklist       : trust the GPU even if Chrome flags it as risky
exec /usr/bin/chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=Translate,TranslateUI,InfiniteSessionRestore \
  --no-first-run \
  --no-default-browser-check \
  --ozone-platform=wayland \
  --enable-features=UseOzonePlatform,CanvasOopRasterization \
  --check-for-update-interval=31536000 \
  --password-store=basic \
  --autoplay-policy=no-user-gesture-required \
  --overscroll-history-navigation=0 \
  --disable-pinch \
  --start-maximized \
  --remote-debugging-port=9222 \
  --remote-allow-origins=* \
  --enable-zero-copy \
  --canvas-oop-rasterization \
  --num-raster-threads=4 \
  --ignore-gpu-blocklist \
  --app="$URL"
