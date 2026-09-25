# HSG Canvas on NixOS

A NixOS configuration for canvas-zolder: a Raspberry Pi 4 Model B with the
Raspberry Pi DAC Pro HAT. It replaces Raspberry Pi OS + `setup.sh` with one
declarative system. The app itself still runs from a git checkout, so
`git pull` + a service restart deploys as before.

| File | Contents |
|---|---|
| `flake.nix` | Inputs (nixos-raspberrypi, disko) and the two install variants |
| `hosts/canvas-zolder.nix` | Hardware, boot, network, audio, Bluetooth |
| `modules/hsg-canvas.nix` | The app and its services (the `setup.sh` part) |
| `modules/appliance.nix` | Reliability: watchdog, snapshots, scrub, SD card wear |
| `lib/layout.nix` | The disk layout, shared by both variants |
| `lib/make-btrfs-subvol-fs.nix` | Builds the btrfs root of the SD image |
| `hosts/btrfs-image.nix` | SD image variant: btrfs root, first-boot resize |
| `hosts/disko-sd.nix` | nixos-anywhere variant: the same layout with disko |

Both variants give the same system and the same disk layout.

## Disk layout

| Partition | Contents |
|---|---|
| `FIRMWARE` (FAT, 1 GB) | `config.txt`, the Raspberry Pi firmware, U-Boot |
| `NIXOS_SD` (btrfs, rest) | Subvolumes `@` → `/`, `@nix` → `/nix`, `@home` → `/home`, `@log` → `/var/log`, `@snapshots` |

All btrfs mounts use `compress=zstd:1,noatime`: less data written to the SD
card, and checksums that detect corruption. The Raspberry Pi vendor kernel has
btrfs (`CONFIG_BTRFS_FS=m`) and zstd.

The SD image builder in nixpkgs makes a flat ext4 or btrfs root.
`lib/make-btrfs-subvol-fs.nix` makes the subvolumes and compresses the data at
build time (`mkfs.btrfs --subvol --compress`, btrfs-progs 6.19 in the pinned
nixpkgs). On the first boot, `expand-root-btrfs` grows the partition and the
filesystem to the size of the card.

## Appliance settings (`modules/appliance.nix`)

- **Hardware watchdog:** the board resets when systemd hangs for 30 s.
- **Kernel panic:** reboot after 10 s.
- **Snapshots:** daily read-only btrbk snapshots of `/home` (the app's `state/`
  with the pairing key, names and stations, `homeassistant.yaml`), kept 7 days,
  in `@snapshots`. The system needs none: NixOS keeps 5 boot generations.
- **Scrub:** a monthly `btrfs scrub` reads every block and reports corruption.
- **SD card wear:** `/tmp` in RAM (the kiosk's Chromium profile lives there),
  a 200 MB journal, weekly Nix garbage collection.
- **Wi-Fi:** power saving off (it drops connections on the Pi's chip).

To restore `state/` from a snapshot:
`sudo cp -a /mnt/btrfs-root/@snapshots/@home.<date>/mike/canvas/state/. /home/mike/canvas/state/`

## Hardware support

Board support comes from [nixos-raspberrypi](https://github.com/nvmd/nixos-raspberrypi):
the Raspberry Pi vendor kernel and firmware, the same as Raspberry Pi OS.

- **DAC Pro HAT:** the firmware applies its overlay from the HAT EEPROM, as on
  Raspberry Pi OS. U-Boot keeps the firmware's device tree
  (`useGenerationDeviceTree = false`), so the overlay survives. Do not switch
  the bootloader to `kernel` without checking `aplay -l`.
- **config.txt:** the same settings as Raspberry Pi OS (`vc4-kms-v3d`,
  `audio=on`, `max_framebuffers=2`, `disable_fw_kms_setup`, `disable_overscan`,
  `arm_boost`), plus the U-Boot `kernel=` line, `enable_uart` and `krnbt`.
- **HDMI and CEC:** vc4 KMS driver, `libcec` for `cec-client`.
- **Bluetooth A2DP sink:** device class 0x200414, always discoverable, the
  no-PIN pairing agent, and the WirePlumber rule from `config/bluetooth`.
- **Audio:** PipeWire with the DAC Pro as the default sink and the larger
  kiosk buffer from `config/pipewire-99-kiosk-buffer.conf`.
- **Wi-Fi:** regulatory domain BE, NetworkManager.

## What runs

The same units as on Raspberry Pi OS, with the same names, because the app
restarts them by name:

- `hsg-canvas`: `start.sh` → FastAPI on :8000, which starts cage + Chromium
- `raspotify`: librespot 0.8 (the version that `raspotify-onevent.sh` expects)
- `sendspin`: the Music Assistant player, installed with `uv tool` on first start
- `bt-auto-agent`, `srs-server` (Docker), nginx on :80 (Angie on Raspberry Pi OS)

Differences from Raspberry Pi OS:

- nginx replaces Angie. The proxy config is the same; nixpkgs has no Angie module.
- `chromium-browser` is a small wrapper around nixpkgs `chromium`.
- The Python venv and the sendspin tool use prebuilt wheels. The services set
  `LD_LIBRARY_PATH` to the C libraries those wheels expect.

## Option A: SD card image (recommended)

Use a **new** SD card. Keep the Raspberry Pi OS card as the fallback.

```bash
cd nix
nix build --accept-flake-config .#images.canvas-zolder   # needs an aarch64 builder or binfmt
zstdcat result/sd-image/*.img.zst | sudo dd of=/dev/sdX bs=4M conv=fsync status=progress
```

Before the first boot, on the new card:

1. Add an SSH key to `users.users.mike.openssh.authorizedKeys.keys` in
   `hosts/canvas-zolder.nix` (do this before the build).
2. Create `/etc/secrets/wifi.env` on the root partition:
   `WIFI_SSID=...` and `WIFI_PSK=...`
3. Copy the runtime files from the old card (see below).

On the first boot, `hsg-canvas-setup` clones the repository and creates the
venv, and `sendspin` installs itself. Both need the network.

Later changes, from a machine with Nix:

```bash
nixos-rebuild switch --flake ./nix#canvas-zolder --target-host mike@canvas-zolder.local --use-remote-sudo
```

## Option B: nixos-anywhere

1. Build and flash the nixos-raspberrypi installer image
   (`nix build github:nvmd/nixos-raspberrypi#installerImages.rpi4`) and boot it.
2. From another machine:
   `nix run github:nix-community/nixos-anywhere -- --flake ./nix#canvas-zolder-anywhere root@<ip>`

This formats the disk in `hosts/disko-sd.nix` (default `/dev/mmcblk0`): GPT
with a hybrid MBR entry for the firmware partition. The Pi 4 boot EEPROM reads
GPT from its 2020 releases on; the MBR entry covers older ones.

## Why not an in-place install over Raspberry Pi OS

nixos-infect and `NIXOS_LUSTRATE` convert a running system in place. On a
Raspberry Pi they must also replace the firmware partition that the running
system boots from. If the new system then does not boot, you need a second
machine to repair the card. A new card with the image has the same result,
and the old card stays a working fallback.

## Runtime files to copy from the old card

These are not in git. Copy them from `/home/mike/canvas` on the old card to the
same place on the new one:

| File | Why |
|---|---|
| `state/` | The Music Assistant pairing key (without it you pair again), device names, station list |
| `cache/` | Station logos (they are looked up again if missing) |
| `overlay_settings.json` | Idle screen background, logo and QR settings |
| `homeassistant.yaml` | Home Assistant URL, token and automations |
| `canvas.conf` | Per-instance settings (host name) |
| `~/.config/sendspin/settings-daemon.json` | The sendspin player settings |

Start `sendspin` with the same `--id` (`sendspinId` in the host file:
`kenwood-speakers`), so Music Assistant keeps the player.

## Check after the first boot

- `aplay -l` shows `card …: Pro [RPi DAC Pro]`
- `ls /dev/dri`: the app starts cage with `WLR_DRM_DEVICES=/dev/dri/card1`
  (`managers/chromium_manager.py`). If vc4 is `card0` on this kernel, change it there.
- `ls /dev/cec*` and `cec-client -l`
- `bluetoothctl show`: Alias, Discoverable yes, Class 0x200414
- `systemctl status hsg-canvas raspotify sendspin bt-auto-agent docker-srs-server nginx`
- The TV shows the canvas, and Spotify, Bluetooth and radio play on the DAC

## Status

- Both variants evaluate with `nix eval` (nixpkgs 26.05, vendor kernel 6.18).
- The generated `config.txt` was compared with the Raspberry Pi OS one.
- `lib/make-btrfs-subvol-fs.nix` was built with the pinned nixpkgs and
  checked: 5 subvolumes, `@` is the default, data zstd-compressed.
- The full SD image was not built, and nothing was booted on hardware yet.
