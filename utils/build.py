"""Hash of the built canvas bundle, used to make kiosks reload after a deploy."""
import os
import re
from typing import Optional

_DIST_INDEX = "frontend/dist/index.html"
_cache = {"mtime": 0.0, "hash": None}


def current_canvas_build() -> Optional[str]:
    """Hash of the currently-built canvas bundle (the `index-<hash>.js` Vite
    emits), parsed from frontend/dist/index.html and cached by mtime.

    The kiosks have no keyboard to hard-refresh, so the React app compares this
    against its own loaded bundle hash (from import.meta.url) and reloads itself
    when the server has a newer build — making every deploy self-propagate.
    """
    try:
        mtime = os.path.getmtime(_DIST_INDEX)
    except OSError:
        return None
    if mtime != _cache["mtime"]:
        try:
            with open(_DIST_INDEX, "r") as fh:
                m = re.search(r"index-([\w-]+)\.js", fh.read())
            _cache["hash"] = m.group(1) if m else None
            _cache["mtime"] = mtime
        except OSError:
            return _cache["hash"]
    return _cache["hash"]
