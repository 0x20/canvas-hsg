# screen-1.local — Pi 3B+ secondary display

A Pi 3B+ that loads `http://canvas.local/canvas/` in a fullscreen browser. No
desktop session, no display manager — boots straight into Chromium under
[`cage`](https://github.com/cage-kiosk/cage) (a minimal wlroots Wayland kiosk),
managed by a systemd service.

Everything in this directory is the source of truth for what runs on
`hsg@screen-1.local` and gets deployed via `install-kiosk.sh`.

## Architecture

```
systemd canvas-kiosk.service
    └─ /usr/local/bin/canvas-kiosk.sh
        └─ cage -- chromium --kiosk --app=$URL  ← this is all that runs
```

No lightdm, no labwc-pi session, no XDG portals, no Wayfire. The Pi boots to
`multi-user.target` and the kiosk service takes over `tty1` as a Wayland session.

## Files

| File | Purpose | Deployed to |
|---|---|---|
| `canvas-kiosk.service` | systemd unit (replaces lightdm autostart) | `/etc/systemd/system/canvas-kiosk.service` |
| `canvas-kiosk.sh` | Cage + Chromium launcher with VC IV-tuned flags | `/usr/local/bin/canvas-kiosk.sh` |
| `install-kiosk.sh` | One-shot installer (idempotent, run with sudo) | _(scp-d to /tmp, run once)_ |

## Boot config

`install-kiosk.sh` writes these into `/boot/firmware/config.txt`:

- `gpu_mem=128` — bumped from the default 76 MB, but capped at 128 (not 256)
  because the Pi 3B+ only has 1 GB RAM total and Chromium is greedy. 256 starved
  the system and caused I/O wait + thrash.
- `gpu_freq=400` — modest V3D overclock from the default 300 MHz.

`/boot/firmware/cmdline.txt` had `overlayroot=tmpfs` set, which silently nuked
all `/etc` and `/home` edits on every reboot. The installer removes it; root
is now writable. (Re-enable later by appending `overlayroot=tmpfs` back to the
single cmdline line if you want corruption-resistance against power cuts.)

`/boot/firmware/kiosk-url.txt` — single-line override of the default URL.

## Deploying changes

```bash
# Stage repo files
scp config/screen-1/{install-kiosk.sh,canvas-kiosk.sh,canvas-kiosk.service} \
    hsg@screen-1.local:/tmp/canvas-kiosk-stage/

# Apply (idempotent; reboots when done)
ssh -t hsg@screen-1.local 'sudo bash /tmp/canvas-kiosk-stage/install-kiosk.sh /tmp/canvas-kiosk-stage'
```

To just reload the launcher without rebooting (after editing `canvas-kiosk.sh`):

```bash
ssh hsg@screen-1.local 'sudo install -m 0755 /tmp/canvas-kiosk-stage/canvas-kiosk.sh /usr/local/bin/ && sudo systemctl restart canvas-kiosk'
```

## Inspecting the kiosk remotely

`canvas-kiosk.sh` passes `--remote-debugging-port=9222 --remote-allow-origins=*`
to Chromium, so from any machine on the LAN you can:

- **DevTools UI**: open `chrome://inspect/#devices` in your local Chrome, click
  "Configure…", add `screen-1.local:9222`. The kiosk page appears under "Remote
  Target" — click "inspect".
- **HTTP introspection**: `curl http://screen-1.local:9222/json/version`.

## Service control

```bash
ssh hsg@screen-1.local 'sudo systemctl status canvas-kiosk'
ssh hsg@screen-1.local 'sudo systemctl restart canvas-kiosk'
ssh hsg@screen-1.local 'sudo journalctl -u canvas-kiosk -f'
```
