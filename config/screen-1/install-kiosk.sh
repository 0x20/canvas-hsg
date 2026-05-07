#!/bin/bash
# HSG Canvas — Pi 3B+ lean-kiosk install (run via sudo on screen-1.local).
#
# What this does, in one shot:
#   1. Disables overlayfs (so /home and /etc edits persist) by removing
#      `overlayroot=tmpfs` from /boot/firmware/cmdline.txt.
#   2. Lowers gpu_mem from 256 → 128 MB in /boot/firmware/config.txt
#      (Pi 3B+ has 1 GB total; 256 starves the system, causing thrash).
#   3. Installs `cage` (minimal wlroots Wayland kiosk).
#   4. Installs canvas-kiosk.service + canvas-kiosk.sh under /etc and
#      /usr/local/bin (the persistent paths now that overlayfs is off).
#   5. Disables lightdm + the desktop autostart, enables canvas-kiosk.
#   6. Schedules a reboot so the new boot path takes over cleanly.
#
# After reboot the Pi boots straight into Chromium fullscreen, no desktop,
# no display manager, no XDG portals.
#
# Idempotent: re-runs are safe.

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "Run this with sudo: sudo bash $0" >&2
  exit 1
fi

REPO_DIR="${1:-$(dirname "$(readlink -f "$0")")}"
echo ">> Using config snippets from: $REPO_DIR"

# 1. cmdline.txt — strip overlayroot=tmpfs
CMD=/boot/firmware/cmdline.txt
if grep -q 'overlayroot=tmpfs' "$CMD"; then
  echo ">> Disabling overlayfs in $CMD"
  cp "$CMD" "$CMD.pre-canvas-kiosk.bak"
  sed -i 's/overlayroot=tmpfs //g' "$CMD"
  sed -i 's/ overlayroot=tmpfs//g' "$CMD"
else
  echo ">> overlayfs already disabled"
fi

# 2. config.txt — gpu_mem=128 (replace 256 if present, otherwise leave alone)
CFG=/boot/firmware/config.txt
if grep -q '^gpu_mem=256' "$CFG"; then
  echo ">> Lowering gpu_mem 256 → 128"
  sed -i 's/^gpu_mem=256/gpu_mem=128/' "$CFG"
elif ! grep -q '^gpu_mem=' "$CFG"; then
  echo ">> Adding gpu_mem=128"
  printf '\n# HSG Canvas\ngpu_mem=128\n' >> "$CFG"
else
  echo ">> gpu_mem already set, leaving alone:"
  grep '^gpu_mem=' "$CFG" | head -1
fi

# 3. cage
if ! command -v cage >/dev/null; then
  echo ">> apt install cage"
  apt-get update -qq
  apt-get install -y --no-install-recommends cage
else
  echo ">> cage already installed"
fi

# 4. systemd unit + launcher script
echo ">> Installing /usr/local/bin/canvas-kiosk.sh"
install -m 0755 "$REPO_DIR/canvas-kiosk.sh" /usr/local/bin/canvas-kiosk.sh
echo ">> Installing /etc/systemd/system/canvas-kiosk.service"
install -m 0644 "$REPO_DIR/canvas-kiosk.service" /etc/systemd/system/canvas-kiosk.service

systemctl daemon-reload

# 5. Boot into multi-user.target (no graphical session), enable kiosk
echo ">> Disabling lightdm + getty@tty1, switching default target to multi-user"
systemctl disable lightdm.service 2>/dev/null || true
# getty@tty1 fights canvas-kiosk for tty1 — disable it so cage can claim the seat.
systemctl disable getty@tty1.service 2>/dev/null || true
systemctl set-default multi-user.target

# Disable the old userland kiosk autostart so it doesn't compete
if [ -f /home/hsg/.config/autostart/kiosk.desktop ]; then
  echo ">> Renaming old kiosk.desktop autostart to .disabled"
  mv /home/hsg/.config/autostart/kiosk.desktop /home/hsg/.config/autostart/kiosk.desktop.disabled
fi

echo ">> Enabling canvas-kiosk.service"
systemctl enable canvas-kiosk.service

# 6. reboot
echo ">> Rebooting in 3s..."
sync
sleep 3
systemctl reboot
