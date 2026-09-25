# A btrfs root filesystem image for sdImage.rootFilesystemCreator, with the
# subvolumes of layout.nix and zstd compression. Based on nixpkgs'
# nixos/lib/make-btrfs-fs.nix, which makes a flat filesystem only.
#
# mkfs.btrfs (btrfs-progs >= 6.x) fills the image from a directory tree: each
# top-level directory named in `subvolumes` becomes a subvolume, and "@" is
# the default subvolume.
{
  pkgs,
  lib,
  storePaths,
  compressImage ? false,
  populateImageCommands ? "",
  volumeLabel,
  uuid ? "44444444-4444-4444-8888-888888888888",
  btrfs-progs,
  libfaketime,
  fakeroot,
  zstd,
}:
let
  layout = import ./layout.nix;
  closure = pkgs.buildPackages.closureInfo { rootPaths = storePaths; };
  # Mount points inside @ for the other subvolumes
  mountDirs = lib.filter (d: d != null && d != "/") (lib.attrValues layout.subvolumes);
  subvolArgs = lib.concatMapStringsSep " " (
    name: if name == "@" then "--subvol default:${name}" else "--subvol rw:${name}"
  ) (lib.attrNames layout.subvolumes);
in
pkgs.stdenv.mkDerivation {
  name = "btrfs-subvol-fs.img${lib.optionalString compressImage ".zst"}";
  nativeBuildInputs = [ btrfs-progs libfaketime fakeroot ] ++ lib.optional compressImage zstd;

  buildCommand = ''
    ${if compressImage then "img=temp.img" else "img=$out"}
    set -x
    (
      mkdir -p ./files
      ${populateImageCommands}
    )

    root=./rootImage
    mkdir -p $root
    ${lib.concatMapStringsSep "\n" (name: "mkdir -p $root/${name}") (lib.attrNames layout.subvolumes)}
    ${lib.concatMapStringsSep "\n" (dir: "mkdir -p $root/@${dir}") mountDirs}

    # The store goes into @nix, which is mounted at /nix
    mkdir -p $root/@nix/store
    xargs -I % cp -a --reflink=auto % -t $root/@nix/store/ < ${closure}/store-paths

    # Everything else goes into @, which is mounted at /
    (
      GLOBIGNORE=".:.."
      shopt -u dotglob
      for f in ./files/*; do
        cp -a --reflink=auto -t $root/@/ "$f"
      done
    )
    cp ${closure}/registration $root/@/nix-path-registration

    touch $img
    faketime -f "1970-01-01 00:00:01" fakeroot mkfs.btrfs \
      -L ${volumeLabel} -U ${uuid} \
      -r $root ${subvolArgs} \
      --compress zstd:1 --shrink $img

    if ! btrfs check $img; then
      echo "--- 'btrfs check' failed for the btrfs image ---"
      exit 1
    fi

    if [ ${toString compressImage} ]; then
      zstd -v --no-progress ./$img -o $out
    fi
  '';
}
