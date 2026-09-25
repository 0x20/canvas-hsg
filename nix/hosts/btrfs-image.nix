# SD image variant: the btrfs root of lib/layout.nix, built by
# lib/make-btrfs-subvol-fs.nix, and a first-boot resize for btrfs.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  layout = import ../lib/layout.nix;
  device = "/dev/disk/by-label/${layout.label}";
in
{
  sdImage = {
    rootVolumeLabel = layout.label;
    rootFilesystemCreator = ../lib/make-btrfs-subvol-fs.nix;
    # The stock first-boot resize runs resize2fs (ext4 only); see below
    expandOnBoot = false;
  };

  # mkForce per mount: it replaces the ext4 root of the SD image module, and
  # keeps the mounts of other modules (appliance.nix: /mnt/btrfs-root)
  fileSystems = lib.mapAttrs (_: lib.mkForce) (
    {
      "/boot/firmware" = {
        device = "/dev/disk/by-label/${config.sdImage.firmwarePartitionName}";
        fsType = "vfat";
        options = [ "noatime" "noauto" "x-systemd.automount" "x-systemd.idle-timeout=1min" ];
      };
    }
    // lib.mapAttrs' (subvol: mountPoint: {
      name = mountPoint;
      value = {
        inherit device;
        fsType = "btrfs";
        options = [ "subvol=${subvol}" ] ++ layout.mountOptions;
      };
    }) (lib.filterAttrs (_: m: m != null) layout.subvolumes)
  );

  # First boot only (the registration file is still there): grow the root
  # partition to the end of the card, then the btrfs filesystem.
  systemd.services.expand-root-btrfs = {
    description = "Grow the root partition and btrfs to fill the SD card";
    unitConfig = {
      DefaultDependencies = false;
      ConditionPathExists = config.sdImage.nixPathRegistrationFile;
    };
    wantedBy = [ "sysinit.target" ];
    before = [ "sysinit.target" "shutdown.target" "register-nix-paths.service" ];
    after = [ "local-fs.target" ];
    conflicts = [ "shutdown.target" ];
    restartIfChanged = false;
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    script = ''
      rootPart=$(${lib.getExe' pkgs.util-linux "findmnt"} -n -o SOURCE --target / | sed 's/\[.*\]$//')
      bootDevice=$(${lib.getExe' pkgs.util-linux "lsblk"} -npo PKNAME $rootPart)
      partNum=$(${lib.getExe' pkgs.util-linux "lsblk"} -npo MAJ:MIN $rootPart | ${lib.getExe pkgs.gawk} -F: '{print $2}')

      echo ",+," | ${lib.getExe' pkgs.util-linux "sfdisk"} -N$partNum --no-reread $bootDevice
      ${lib.getExe' pkgs.parted "partprobe"}
      ${lib.getExe' pkgs.btrfs-progs "btrfs"} filesystem resize max /
    '';
  };
}
