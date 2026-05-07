#!/bin/bash
# HSG Canvas — lean kiosk launcher for the Pi 3B+ secondary display.
# No desktop session, no XDG portals. Just cage running Chromium fullscreen
# under wlroots → DRM → HDMI. Started by canvas-kiosk.service on tty1.

set -e

URL_FILE=/boot/firmware/kiosk-url.txt
DEFAULT_URL="http://canvas.local/canvas/"
URL=$(cat "$URL_FILE" 2>/dev/null | tr -d '[:space:]')
[ -z "$URL" ] && URL="$DEFAULT_URL"

# Wait for the canvas server to be reachable (max ~60s) so Chromium doesn't
# load an error page on boot before networking is up.
for _ in $(seq 1 30); do
  curl -sSf -o /dev/null --max-time 2 "$URL" && break
  sleep 2
done

# Suppress the "Chrome didn't shut down correctly" prompt after a power cut.
PREFS="$HOME/.config/chromium/Default/Preferences"
if [ -f "$PREFS" ]; then
  sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"Crashed"/"exit_type":"Normal"/' "$PREFS"
fi

# cage = minimal wlroots Wayland kiosk. Runs the given client fullscreen and
# exits when the client exits (systemd will restart us).
exec /usr/bin/cage -- /usr/bin/chromium \
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
  --enable-gpu-rasterization \
  --use-gl=egl \
  --use-angle=gles \
  --app="$URL"
