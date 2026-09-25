"""
The device names the canvas announces, kept in state/names.env.

systemd reads this file as an EnvironmentFile for raspotify (LIBRESPOT_NAME)
and the sendspin daemon (SENDSPIN_NAME), so a name set from the control panel
wins over the defaults that setup.sh writes. The file lives in the app
directory, so the app never writes to /etc.
"""
import os
import re
from typing import Dict

NAMES_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state", "names.env"
)

# Printable, no quotes, backslashes or $ (they would need escaping in systemd)
_VALID_NAME = re.compile(r'^[^"\'\\$`\x00-\x1f]{1,40}$')
_LINE = re.compile(r'^([A-Z_]+)="(.*)"$')


def valid_name(name: str) -> bool:
    return bool(_VALID_NAME.match(name)) and name == name.strip()


def read_names() -> Dict[str, str]:
    try:
        with open(NAMES_ENV_PATH) as f:
            return {m.group(1): m.group(2) for line in f if (m := _LINE.match(line.strip()))}
    except OSError:
        return {}


def write_name(key: str, name: str) -> None:
    if not valid_name(name):
        raise ValueError("A name has 1-40 characters, without quotes, backslashes or $")
    names = read_names()
    names[key] = name
    os.makedirs(os.path.dirname(NAMES_ENV_PATH), exist_ok=True)
    tmp = NAMES_ENV_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write("# Written by the HSG Canvas control panel. Read by systemd.\n")
        for k, v in sorted(names.items()):
            f.write(f'{k}="{v}"\n')
    os.replace(tmp, NAMES_ENV_PATH)
