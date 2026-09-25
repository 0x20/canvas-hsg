# Reliability settings for an unattended appliance on an SD card. Used by both
# the SD image and the nixos-anywhere install.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  layout = import ../lib/layout.nix;
in
{
  # ── Recover without a person ─────────────────────────────────────────

  # The BCM2835 hardware watchdog resets the board when systemd hangs
  systemd.settings.Manager = {
    RuntimeWatchdogSec = "30s";
    RebootWatchdogSec = "2min";
  };

  # Reboot 10 s after a kernel panic or oops, not hang
  boot.kernel.sysctl = {
    "kernel.panic" = 10;
    "kernel.panic_on_oops" = 1;
  };

  # Wi-Fi power saving drops connections on the Pi's brcmfmac chip
  networking.networkmanager.wifi.powersave = false;

  # ── btrfs ────────────────────────────────────────────────────────────

  boot.supportedFilesystems.btrfs = true;
  boot.initrd.supportedFilesystems.btrfs = true;

  # Checksums detect SD card corruption; a monthly scrub reads every block
  services.btrfs.autoScrub = {
    enable = true;
    interval = "monthly";
    fileSystems = [ "/" ];
  };

  # The top level of the btrfs filesystem, for the snapshots below
  fileSystems."/mnt/btrfs-root" = {
    device = "/dev/disk/by-label/${layout.label}";
    fsType = "btrfs";
    options = [ "subvolid=5" "noatime" "x-systemd.automount" "x-systemd.idle-timeout=5min" ];
  };

  # Daily read-only snapshots of /home: the app's state/ (the Music Assistant
  # pairing key, device names, station list), homeassistant.yaml and the
  # sendspin settings. Kept 7 days. The system itself needs no snapshots:
  # NixOS keeps boot generations.
  services.btrbk.instances.home = {
    onCalendar = "daily";
    settings = {
      snapshot_preserve_min = "2d";
      snapshot_preserve = "7d";
      volume."/mnt/btrfs-root" = {
        snapshot_dir = "@snapshots";
        subvolume."@home" = { };
      };
    };
  };

  # ── SD card wear and space ───────────────────────────────────────────

  # /tmp in RAM: the kiosk's Chromium profile (/tmp/chromium-hsg-canvas) and
  # logs stop writing to the card. 25 % of the Pi's 2 GB; zram swap backs it.
  boot.tmp = {
    useTmpfs = true;
    tmpfsSize = "25%";
  };

  services.journald.extraConfig = ''
    SystemMaxUse=200M
    MaxRetentionSec=1month
  '';

  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 14d";
  };
  nix.optimise.automatic = true;

  # Older generations stay bootable; limit them so /boot does not fill up
  boot.loader.generic-extlinux-compatible.configurationLimit = 5;
}
