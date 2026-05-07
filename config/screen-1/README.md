# screen-1.local — Pi 3B+ secondary display

Configuration for the Pi 3B+ remote kiosk that loads `http://canvas.local/canvas/`
(the React canvas served by the primary HSG Canvas Pi).

This directory snapshots what's deployed on `hsg@screen-1.local` so the device
is reproducible. Anything here is also a hand-deploy target — there's no
`setup.sh` for the secondary device yet.

## Files

- `kiosk.sh` — autostarted by `~/.config/autostart/kiosk.desktop`. Launches
  Chromium in kiosk mode under labwc/wlroots with GPU-friendly flags tuned for
  VideoCore IV (Pi 3B+). Deployed to `/home/hsg/.local/bin/kiosk.sh`.
- `config.txt.fragment` — additions to `/boot/firmware/config.txt`. The big
  one is `gpu_mem=256` — Chromium's GPU process is starved at the default 76 MB.

## Deploying changes

```bash
# kiosk.sh
scp config/screen-1/kiosk.sh hsg@screen-1.local:/home/hsg/.local/bin/kiosk.sh
ssh hsg@screen-1.local 'chmod +x /home/hsg/.local/bin/kiosk.sh && pkill -f "chromium.*--kiosk" || true'
# Chromium will be restarted by the autostart entry on next session;
# easiest way to apply is `sudo systemctl restart lightdm` on the Pi.

# config.txt fragment (requires reboot)
ssh hsg@screen-1.local 'sudo bash -c "cat /home/hsg/srs_server/config/screen-1/config.txt.fragment >> /boot/firmware/config.txt && reboot"'
# (only if the repo is checked out on the Pi; otherwise scp the fragment first)
```

## What lives where

| Pi 3B+ path | What | Source in repo |
|---|---|---|
| `/home/hsg/.local/bin/kiosk.sh` | Chromium kiosk launcher | `config/screen-1/kiosk.sh` |
| `~/.config/autostart/kiosk.desktop` | Autostart entry that calls `kiosk.sh` | _(not in repo, hand-installed)_ |
| `/boot/firmware/config.txt` | Boot config (GPU mem, overclock, dtoverlays) | `config/screen-1/config.txt.fragment` |
| `/boot/firmware/kiosk-url.txt` | Override URL (one line, no spaces). If absent, falls back to `DEFAULT_URL` in kiosk.sh | _(not in repo, per-device)_ |

## Inspecting the kiosk remotely

`kiosk.sh` passes `--remote-debugging-port=9222 --remote-allow-origins=*` to
Chromium, so from any machine on the LAN you can:

- **DevTools UI**: open `chrome://inspect/#devices` in your local Chrome,
  click "Configure…", add `screen-1.local:9222`. The kiosk page appears under
  "Remote Target" — click "inspect".
- **HTTP introspection**: `curl http://screen-1.local:9222/json/version`.
