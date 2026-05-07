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

# Mode lock: drop the display to 1280x720 @ 60 Hz so chromium's compositor
# can hit every vsync. Native (1920x1080@60) on VC IV was oscillating
# 30-60 fps with visible stutter (~124 MP/s pixel work hits the fillrate
# wall). At 720p that drops to ~55 MP/s and the scene sustains a flat
# 60 fps. Override by putting one line ("1920x1080@60", "1280x720@50",
# etc.) in the file at /boot/firmware/canvas-display-mode.txt.
MODE_FILE=/boot/firmware/canvas-display-mode.txt
DEFAULT_MODE="1280x720@60"
MODE=$(cat "$MODE_FILE" 2>/dev/null | tr -d '[:space:]')
[ -z "$MODE" ] && MODE="$DEFAULT_MODE"

# Stash a wrapper that cage will exec. The wrapper backgrounds a small
# wlr-randr loop (waits for the wayland socket to come up, sets the mode,
# exits) and then exec's chromium with the kiosk flags.
WRAPPER=$(mktemp /tmp/canvas-kiosk-wrap.XXXXXX.sh)
trap "rm -f $WRAPPER" EXIT
cat > "$WRAPPER" <<EOF
#!/bin/bash
# Set output mode once cage's wayland socket is ready
(
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    OUT=\$(XDG_RUNTIME_DIR=/run/user/\$(id -u) wlr-randr 2>/dev/null | head -1 | awk '{print \$1}')
    if [ -n "\$OUT" ]; then
      XDG_RUNTIME_DIR=/run/user/\$(id -u) wlr-randr --output "\$OUT" --mode "$MODE" >/dev/null 2>&1
      break
    fi
  done
) &
exec /usr/bin/chromium \\
  --kiosk \\
  --noerrdialogs \\
  --disable-infobars \\
  --disable-session-crashed-bubble \\
  --disable-features=Translate,TranslateUI,InfiniteSessionRestore \\
  --no-first-run \\
  --no-default-browser-check \\
  --ozone-platform=wayland \\
  --enable-features=UseOzonePlatform,CanvasOopRasterization \\
  --check-for-update-interval=31536000 \\
  --password-store=basic \\
  --autoplay-policy=no-user-gesture-required \\
  --overscroll-history-navigation=0 \\
  --disable-pinch \\
  --start-maximized \\
  --remote-debugging-port=9222 \\
  --remote-allow-origins=* \\
  --enable-zero-copy \\
  --canvas-oop-rasterization \\
  --num-raster-threads=4 \\
  --ignore-gpu-blocklist \\
  --enable-gpu-rasterization \\
  --use-gl=egl \\
  --use-angle=gles \\
  --app="$URL"
EOF
chmod +x "$WRAPPER"

# cage = minimal wlroots Wayland kiosk. Runs the wrapper fullscreen and
# exits when the client exits (systemd will restart us).
exec /usr/bin/cage -- "$WRAPPER"
