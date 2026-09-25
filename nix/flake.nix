{
  description = "HSG Canvas on NixOS (Raspberry Pi 4 with the Raspberry Pi DAC Pro HAT)";

  # Prebuilt vendor kernel and firmware; without this the first build compiles
  # the Raspberry Pi kernel, which takes hours.
  nixConfig = {
    extra-substituters = [ "https://nixos-raspberrypi.cachix.org" ];
    extra-trusted-public-keys = [
      "nixos-raspberrypi.cachix.org-1:4iMO9LXa8BqhU+Rpg6LQKiGa2lsNh/j2oiYLNOQ5sPI="
    ];
  };

  inputs = {
    # Raspberry Pi vendor kernel, firmware and config.txt management
    nixos-raspberrypi.url = "github:nvmd/nixos-raspberrypi/main";
    # Same nixpkgs as the board support, so the binary cache matches
    nixpkgs.follows = "nixos-raspberrypi/nixpkgs";

    disko = {
      url = "github:nix-community/disko";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      nixos-raspberrypi,
      disko,
      ...
    }@inputs:
    let
      canvas =
        extraModules:
        nixos-raspberrypi.lib.nixosSystem {
          specialArgs = inputs;
          modules = [
            ./hosts/canvas-zolder.nix
            ./modules/hsg-canvas.nix
            ./modules/appliance.nix
          ] ++ extraModules;
        };
    in
    {
      nixosConfigurations = {
        # SD card image: build, flash, boot. Also the target for later
        # `nixos-rebuild switch --target-host`.
        canvas-zolder = canvas [
          nixos-raspberrypi.nixosModules.sd-image
          ./hosts/btrfs-image.nix
        ];

        # Same system, installed over the network with nixos-anywhere onto a
        # Pi that runs the nixos-raspberrypi installer image (see README).
        canvas-zolder-anywhere = canvas [
          disko.nixosModules.disko
          ./hosts/disko-sd.nix
        ];
      };

      # nix build .#images.canvas-zolder
      images.canvas-zolder = self.nixosConfigurations.canvas-zolder.config.system.build.sdImage;
    };
}
