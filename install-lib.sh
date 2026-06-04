#!/bin/bash
# Shared helpers for the HSG Canvas install scripts (setup.sh, install-services.sh).
# Source this after defining SCRIPT_DIR:
#     SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
#     source "$SCRIPT_DIR/install-lib.sh"
#     detect_install_user

# Resolve the install user/group/home/uid (the sudo invoker, not root) into the
# ACTUAL_USER / USER_HOME / ACTUAL_GROUP / ACTUAL_UID variables used by render_unit.
detect_install_user() {
    ACTUAL_USER=${SUDO_USER:-$USER}
    USER_HOME=$(eval echo ~$ACTUAL_USER)
    ACTUAL_GROUP=$(id -gn "$ACTUAL_USER")
    ACTUAL_UID=$(id -u "$ACTUAL_USER")
}

# Render a systemd unit / drop-in from the repo, substituting the canonical hsg
# deployment values (user, group, repo path, uid) with this install's. Keeps the
# checked-in files readable as the hsg reference while letting the canvas install
# under any user/path. Requires SCRIPT_DIR + the detect_install_user vars.
#   render_unit <src> <dest>
render_unit() {
    sed -e "s#/home/hsg/srs_server#$SCRIPT_DIR#g" \
        -e "s#/home/hsg#$USER_HOME#g" \
        -e "s#^User=hsg\$#User=$ACTUAL_USER#" \
        -e "s#^Group=hsg\$#Group=$ACTUAL_GROUP#" \
        -e "s#/run/user/1000#/run/user/$ACTUAL_UID#g" \
        "$1" > "$2"
}
