# The boot disk layout, shared by the SD image (make-btrfs-subvol-fs.nix,
# hosts/btrfs-image.nix) and the nixos-anywhere install (hosts/disko-sd.nix),
# so both give the same system.
{
  # Filesystem label of the btrfs root; the firmware partition is FIRMWARE
  label = "NIXOS_SD";

  # Subvolume -> mount point. @snapshots holds the btrbk snapshots and is only
  # reached through the top-level mount (see modules/appliance.nix).
  subvolumes = {
    "@" = "/";
    "@nix" = "/nix";
    "@home" = "/home";
    "@log" = "/var/log";
    "@snapshots" = null;
  };

  # zstd:1: less data written to the SD card at a low CPU cost.
  # noatime: no write for each read.
  mountOptions = [ "compress=zstd:1" "noatime" ];
}
