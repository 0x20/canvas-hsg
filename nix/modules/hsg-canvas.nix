# The HSG Canvas services, the NixOS equivalent of setup.sh:
# - hsg-canvas: the FastAPI app (start.sh), which starts the cage + Chromium kiosk
# - raspotify: Spotify Connect (librespot), the unit name the app restarts
# - sendspin: the Music Assistant player daemon
# - bt-auto-agent: accepts Bluetooth pairing without a PIN
# - srs-server: the SRS streaming server container
# - nginx on port 80 in front of the app (Angie on Raspberry Pi OS)
#
# The app runs from a git checkout with its own Python venv (uv), as on
# Raspberry Pi OS, so `git pull` + restart deploys as before. The venv and the
# sendspin tool use prebuilt wheels; LD_LIBRARY_PATH gives them the C
# libraries they expect from a normal Linux system.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.hsg-canvas;
  home = config.users.users.${cfg.user}.home;
  uid = toString config.users.users.${cfg.user}.uid;
  repo = cfg.repoDir;
  runtimeDir = "/run/user/${uid}";

  python = pkgs.python313;

  # The app starts "chromium-browser" (the Debian name)
  chromiumBrowser = pkgs.writeShellScriptBin "chromium-browser" ''
    exec ${pkgs.chromium}/bin/chromium "$@"
  '';

  # C libraries for prebuilt Python wheels (Pillow, pydantic-core, aiohttp,
  # sounddevice/PortAudio for sendspin, ...)
  wheelLibs = lib.makeLibraryPath (with pkgs; [
    stdenv.cc.cc.lib
    zlib
    libffi
    openssl
    portaudio
    libopus
    flac
    libsndfile
    alsa-lib
    libpulseaudio
  ]);

  # Programs the app and its scripts call (see utils/proc.py call sites)
  appPath = with pkgs; [
    bash
    coreutils
    findutils
    gnugrep
    gnused
    procps
    psmisc
    curl
    jq
    git
    nodejs_22
    uv
    python
    cage
    chromiumBrowser
    pulseaudio
    alsa-utils
    bluez
    dbus
    systemd
    libcec
    iproute2
    "/run/wrappers"
  ];

  userEnv = {
    HOME = home;
    XDG_RUNTIME_DIR = runtimeDir;
    PULSE_SERVER = "unix:${runtimeDir}/pulse/native";
    DBUS_SESSION_BUS_ADDRESS = "unix:path=${runtimeDir}/bus";
    LD_LIBRARY_PATH = wheelLibs;
  };

  # The same Python for the venv and for sendspin; no uv-managed interpreters
  pythonEnv = {
    UV_PYTHON = "${python}/bin/python3";
    UV_PYTHON_DOWNLOADS = "never";
  };

  btAgentPython = pkgs.python3.withPackages (ps: [ ps.dbus-python ps.pygobject3 ]);
in
{
  options.services.hsg-canvas = {
    enable = lib.mkEnableOption "the HSG Canvas display and audio services";

    user = lib.mkOption {
      type = lib.types.str;
      default = "hsg";
      description = "User that runs the app, the kiosk, PipeWire, librespot and sendspin.";
    };

    repoDir = lib.mkOption {
      type = lib.types.str;
      default = "${config.users.users.${cfg.user}.home}/canvas";
      defaultText = lib.literalExpression ''"''${home}/canvas"'';
      description = "Git checkout of the canvas-hsg repository. state/ and cache/ live here.";
    };

    repoUrl = lib.mkOption {
      type = lib.types.str;
      default = "https://github.com/0x20/canvas-hsg.git";
      description = "Cloned into repoDir on the first boot when it does not exist.";
    };

    spotifyName = lib.mkOption {
      type = lib.types.str;
      default = "HSG Canvas";
      description = "Default Spotify Connect name. A name set in the control panel (state/names.env) wins.";
    };

    sendspinName = lib.mkOption {
      type = lib.types.str;
      default = "HSG Canvas";
      description = "Default Music Assistant player name. A name set in the control panel wins.";
    };

    sendspinId = lib.mkOption {
      type = lib.types.str;
      default = "hsg-canvas";
      description = "Sendspin client id. Keep it stable: Music Assistant knows the player by it.";
    };

    spotifyZeroconfPort = lib.mkOption {
      type = lib.types.port;
      default = 4070;
      description = "Fixed librespot discovery port, so the firewall can allow it.";
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.${cfg.user} = {
      isNormalUser = true;
      # PipeWire and the other user services run without a login
      linger = true;
      extraGroups = [ "audio" "video" "render" "input" "seat" "bluetooth" ];
    };

    # cage needs a seat without a logged-in user; the app uses /run/seatd.sock
    services.seatd.enable = true;

    # The app restarts these after a rename or when librespot hangs
    # (routes/settings.py, main.py). Same rules as config/sudoers.d/hsg-canvas.
    security.sudo.extraRules = [
      {
        users = [ cfg.user ];
        commands = map (service: {
          command = "/run/current-system/sw/bin/systemctl restart ${service}";
          options = [ "NOPASSWD" ];
        }) [ "raspotify" "sendspin" ];
      }
    ];

    # First boot: clone the repository and create the Python venv; later boots
    # only update the venv when requirements.txt changed.
    systemd.services.hsg-canvas-setup = {
      description = "HSG Canvas checkout and Python venv";
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      path = with pkgs; [ git uv coreutils ];
      environment = userEnv // pythonEnv;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        User = cfg.user;
      };
      script = ''
        set -eu
        if [ ! -d ${repo}/.git ]; then
          git clone ${cfg.repoUrl} ${repo}
        fi
        cd ${repo}
        if [ ! -f .venv/.requirements-done ] || [ requirements.txt -nt .venv/.requirements-done ]; then
          uv venv --allow-existing .venv
          uv pip install --python .venv/bin/python -r requirements.txt
          touch .venv/.requirements-done
        fi
        mkdir -p state cache
      '';
    };

    systemd.services.hsg-canvas = {
      description = "HSG Canvas - media, display and control panel";
      wantedBy = [ "multi-user.target" ];
      requires = [ "hsg-canvas-setup.service" ];
      after = [
        "hsg-canvas-setup.service"
        "network-online.target"
        "seatd.service"
        "user@${uid}.service"
      ];
      wants = [ "network-online.target" "user@${uid}.service" ];
      path = appPath;
      environment = userEnv // { SEATD_SOCK = "/run/seatd.sock"; };
      serviceConfig = {
        User = cfg.user;
        WorkingDirectory = repo;
        # start.sh builds the frontend when needed and runs main.py
        ExecStart = "${repo}/start.sh";
        Restart = "always";
        RestartSec = 10;
        # cage opens the DRM device through seatd; keep /tmp shared for the
        # Chromium profile and the librespot event log
        PrivateTmp = false;
      };
    };

    # Spotify Connect. Same unit name and environment as Raspberry Pi OS's
    # raspotify, which the app and the watchdog restart by that name.
    systemd.services.raspotify = {
      description = "Spotify Connect (librespot)";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" "user@${uid}.service" ];
      after = [ "network-online.target" "sound.target" "user@${uid}.service" ];
      # raspotify-onevent.sh uses bash, jq and curl
      path = with pkgs; [ bash coreutils jq curl ];
      environment = userEnv // {
        LIBRESPOT_NAME = cfg.spotifyName;
        LIBRESPOT_BACKEND = "pulseaudio";
        LIBRESPOT_BITRATE = "320";
        LIBRESPOT_DEVICE_TYPE = "speaker";
        LIBRESPOT_INITIAL_VOLUME = "70";
        LIBRESPOT_ONEVENT = "${repo}/raspotify-onevent.sh";
        LIBRESPOT_ZEROCONF_PORT = toString cfg.spotifyZeroconfPort;
        LIBRESPOT_CACHE = "/var/cache/raspotify";
      };
      serviceConfig = {
        User = cfg.user;
        # LIBRESPOT_NAME from the control panel overrides the default above
        EnvironmentFile = "-${repo}/state/names.env";
        ExecStart = "${pkgs.librespot}/bin/librespot";
        CacheDirectory = "raspotify";
        Restart = "always";
        RestartSec = 10;
      };
    };

    # Music Assistant player. The daemon is installed with uv as on Raspberry Pi
    # OS (`uv tool install sendspin`), because it is not packaged in nixpkgs.
    systemd.services.sendspin = {
      description = "Sendspin Multi-Room Audio Client";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" "user@${uid}.service" ];
      after = [ "network-online.target" "sound.target" "user@${uid}.service" "hsg-canvas-setup.service" ];
      path = with pkgs; [ uv curl coreutils ];
      environment = userEnv // pythonEnv // { SENDSPIN_NAME = cfg.sendspinName; };
      serviceConfig = {
        User = cfg.user;
        # SENDSPIN_NAME from the control panel overrides the default above
        EnvironmentFile = "-${repo}/state/names.env";
        ExecStartPre = pkgs.writeShellScript "sendspin-install" ''
          [ -x ${home}/.local/bin/sendspin ] || uv tool install sendspin@latest
        '';
        # ''${SENDSPIN_NAME} stays one argument with spaces
        ExecStart = lib.concatStringsSep " " [
          "${home}/.local/bin/sendspin daemon"
          "--name \${SENDSPIN_NAME}"
          "--id ${cfg.sendspinId}"
          "--audio-device pulse"
          "--hook-start \"curl -s -X POST http://127.0.0.1:8000/sendspin/hook/start\""
          "--hook-stop \"curl -s -X POST http://127.0.0.1:8000/sendspin/hook/stop\""
        ];
        Restart = "on-failure";
        RestartSec = 10;
      };
    };

    systemd.services.bt-auto-agent = {
      description = "Bluetooth agent that accepts pairing without a PIN";
      wantedBy = [ "multi-user.target" ];
      after = [ "bluetooth.service" "hsg-canvas-setup.service" ];
      requires = [ "bluetooth.service" ];
      path = [ pkgs.bluez ];
      serviceConfig = {
        ExecStartPre = [
          "${pkgs.bluez}/bin/bluetoothctl discoverable on"
          "${pkgs.bluez}/bin/bluetoothctl pairable on"
        ];
        ExecStart = "${btAgentPython}/bin/python3 ${repo}/config/bluetooth/bt-auto-agent.py";
        Restart = "always";
        RestartSec = 5;
      };
    };

    # SRS (Simple Realtime Server): RTMP in, HTTP-FLV/HLS out
    virtualisation.docker.enable = true;
    virtualisation.oci-containers = {
      backend = "docker";
      containers.srs-server = {
        image = "ossrs/srs:4";
        cmd = [ "./objs/srs" "-c" "conf/docker.conf" ];
        ports = [ "1935:1935" "1985:1985" "8080:8080" ];
      };
    };

    # Port 80 -> the app; the loading page covers restarts (config/angie)
    services.nginx = {
      enable = true;
      recommendedProxySettings = false;
      upstreams.fastapi.servers."127.0.0.1:8000" = { };
      virtualHosts.canvas = {
        default = true;
        listen = [ { addr = "0.0.0.0"; port = 80; } ];
        extraConfig = ''
          error_page 502 503 504 = /__hsg_loading;
        '';
        locations."= /__hsg_loading" = {
          alias = "${../../config/angie/loading.html}";
          extraConfig = ''
            internal;
            default_type text/html;
            add_header Cache-Control "no-store";
          '';
        };
        locations."/" = {
          proxyPass = "http://fastapi";
          proxyWebsockets = true;
          extraConfig = ''
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_intercept_errors on;
          '';
        };
      };
    };

    networking.firewall = {
      allowedTCPPorts = [
        80 # control panel and canvas
        8928 # sendspin player (Music Assistant connects to it)
        8930 # sendspin artwork client
        1935 1985 8080 # SRS
        cfg.spotifyZeroconfPort
      ];
      allowedUDPPorts = [ 5353 ]; # mDNS: Chromecast, Spotify Connect, Music Assistant
    };
  };
}
