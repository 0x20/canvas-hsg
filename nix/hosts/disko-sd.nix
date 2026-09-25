# Boot disk layout for nixos-anywhere: a FAT firmware partition (config.txt,
# firmware, U-Boot) and the btrfs root of lib/layout.nix, as in the SD image.
#
# GPT with a hybrid MBR entry for the firmware partition: the Pi 4 boot EEPROM
# reads GPT (bootloader from 2020 on), and the MBR entry covers older firmware.
{ lib, ... }:
let
  layout = import ../lib/layout.nix;
in
{
  disko.devices.disk.sd = {
    type = "disk";
    # Change for an NVMe or USB boot disk
    device = lib.mkDefault "/dev/mmcblk0";
    content = {
      type = "gpt";
      efiGptPartitionFirst = false;
      partitions = {
        FIRMWARE = {
          priority = 1;
          type = "0700"; # Microsoft basic data (FAT)
          size = "1G";
          hybrid = {
            mbrPartitionType = "0x0c"; # FAT32 LBA
            mbrBootableFlag = true;
          };
          content = {
            type = "filesystem";
            format = "vfat";
            extraArgs = [ "-n" "FIRMWARE" ];
            mountpoint = "/boot/firmware";
            mountOptions = [ "noatime" "noauto" "x-systemd.automount" "x-systemd.idle-timeout=1min" ];
          };
        };
        root = {
          size = "100%";
          content = {
            type = "btrfs";
            extraArgs = [ "-L" layout.label "-f" ];
            subvolumes = lib.mapAttrs (_: mountPoint: {
              mountpoint = mountPoint;
              mountOptions = layout.mountOptions;
            }) layout.subvolumes;
          };
        };
      };
    };
  };
}
