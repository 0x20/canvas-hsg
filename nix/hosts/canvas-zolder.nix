# canvas-zolder: Raspberry Pi 4 Model B with the Raspberry Pi DAC Pro HAT,
# HDMI to the TV, Wi-Fi, Bluetooth A2DP sink.
#
# Hardware notes (read from the Raspberry Pi OS install on 2026-09-25):
# - config.txt there: dtparam=audio=on, dtoverlay=vc4-kms-v3d,
#   max_framebuffers=2, disable_fw_kms_setup=1, disable_overscan=1, arm_boost=1.
# - The DAC Pro has no dtoverlay line: the firmware reads the HAT EEPROM and
#   applies its overlay. That keeps working here because U-Boot boots with the
#   device tree the firmware built (useGenerationDeviceTree = false).
# - ALSA card "Pro" (pcm512x); PipeWire sink alsa_output.platform-soc_sound.*
{
  config,
  lib,
  pkgs,
  nixos-raspberrypi,
  ...
}:
{
  imports = with nixos-raspberrypi.nixosModules; [
    raspberry-pi-4.base
    raspberry-pi-4.display-vc4
    raspberry-pi-4.bluetooth
  ];

  system.stateVersion = "26.05";
  networking.hostName = "canvas-zolder";
  time.timeZone = "Europe/Brussels";
  i18n.defaultLocale = "en_US.UTF-8";

  # ── Boot and firmware ────────────────────────────────────────────────

  boot.loader.raspberry-pi = {
    bootloader = "uboot";
    # Keep the firmware's device tree: it holds the HAT EEPROM overlay (DAC Pro)
    # and the config.txt overlays. Do not switch to "kernel" without checking
    # that the DAC still shows up in `aplay -l`.
    useGenerationDeviceTree = false;
  };

  # The same config.txt as Raspberry Pi OS. dtparam=audio=on, vc4-kms-v3d and
  # arm_boost are the module defaults already.
  hardware.raspberry-pi.config.all.options = {
    max_framebuffers = { enable = true; value = 2; };
    disable_fw_kms_setup = { enable = true; value = 1; };
    disable_overscan = { enable = true; value = 1; };
    # The DAC Pro loads from its EEPROM. If a board ever has a HAT without an
    # EEPROM, add under hardware.raspberry-pi.config.all.dt-overlays:
    #   rpi-dacpro = { enable = true; params = { }; };
  };

  boot.kernelParams = [ "cfg80211.ieee80211_regdom=BE" ];

  zramSwap.enable = true;

  # The SD image base profile adds ZFS; this Pi does not use it
  boot.supportedFilesystems.zfs = lib.mkForce false;

  # Filesystems: btrfs with subvolumes, see lib/layout.nix; reliability
  # settings in modules/appliance.nix

  # ── Network ──────────────────────────────────────────────────────────

  networking.networkmanager.enable = true;
  # The Wi-Fi profile is not in git. Put the PSK in /etc/secrets/wifi.env on
  # the SD card (WIFI_SSID=... and WIFI_PSK=...) before the first boot, or
  # connect once with `nmcli device wifi connect <ssid> password <psk>`.
  networking.networkmanager.ensureProfiles = {
    environmentFiles = [ "/etc/secrets/wifi.env" ];
    profiles.space-wifi = {
      connection = { id = "space-wifi"; type = "wifi"; };
      wifi = { mode = "infrastructure"; ssid = "$WIFI_SSID"; };
      wifi-security = { key-mgmt = "wpa-psk"; psk = "$WIFI_PSK"; };
      ipv4.method = "auto";
      ipv6.method = "auto";
    };
  };

  # canvas-zolder.local: the kiosk URL, the QR code and Music Assistant need it
  services.avahi = {
    enable = true;
    nssmdns4 = true;
    publish = { enable = true; addresses = true; workstation = true; };
  };

  services.openssh = {
    enable = true;
    settings.PasswordAuthentication = false;
  };

  # ── Graphics, audio, Bluetooth ───────────────────────────────────────

  hardware.graphics.enable = true;

  security.rtkit.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    pulse.enable = true;
    wireplumber.enable = true;
    # A larger buffer survives CPU and thermal spikes (the Pi 4 throttles near
    # 80 °C); config/pipewire-99-kiosk-buffer.conf
    extraConfig.pipewire."99-kiosk-buffer"."context.properties" = {
      "default.clock.rate" = 48000;
      "default.clock.quantum" = 2048;
      "default.clock.min-quantum" = 2048;
      "default.clock.max-quantum" = 4096;
    };
    wireplumber.extraConfig = {
      # The DAC Pro is the speaker output for every source
      "50-hsg-dac-default" = {
        "monitor.alsa.rules" = [
          {
            matches = [ { "node.name" = "~alsa_output.platform-soc_sound.*"; } ];
            actions.update-props = {
              "priority.session" = 2000;
              "priority.driver" = 2000;
            };
          }
        ];
      };
      # Incoming Bluetooth A2DP audio goes to the speakers (the Lua rule
      # config/bluetooth/51-hsg-bluetooth.lua, in WirePlumber 0.5 syntax)
      "51-hsg-bluetooth" = {
        "monitor.bluez.rules" = [
          {
            matches = [ { "node.name" = "~bluez_input.*"; } ];
            actions.update-props = { "media.class" = "Audio/Source"; };
          }
        ];
      };
    };
  };

  hardware.bluetooth = {
    enable = true;
    powerOnBoot = true;
    settings = {
      General = {
        Name = "HSG Canvas";
        # Audio / loudspeaker device class, so phones list it as a speaker
        Class = "0x200414";
        DiscoverableTimeout = 0;
        Pairable = true;
      };
      Policy.AutoEnable = true;
    };
  };

  environment.systemPackages = with pkgs; [
    git
    htop
    alsa-utils
    pulseaudio # pactl
    libcec # cec-client
    raspberrypi-utils
  ];

  # ── The canvas ───────────────────────────────────────────────────────

  services.hsg-canvas = {
    enable = true;
    user = "mike";
    repoUrl = "https://github.com/0x20/canvas-hsg.git";
    sendspinName = "Kenwood Speakers";
    sendspinId = "kenwood-speakers";
  };

  users.users.mike = {
    isNormalUser = true;
    uid = 1000;
    extraGroups = [ "wheel" "networkmanager" ];
    # Add the SSH keys that may log in
    openssh.authorizedKeys.keys = [ ];
  };
  security.sudo.wheelNeedsPassword = false;

  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    trusted-users = [ "root" "@wheel" ];
  };
}
