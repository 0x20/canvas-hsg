"""
Track info: the artist and title that a radio station plays now.

Two jobs:
- fetch(): read the current track with a known method.
- detect(): find a method for a station, with rules only (no guesswork by AI):
    1. a known provider, recognized by the stream URL (SomaFM, FIP, BBC, ...)
    2. ICY titles in the stream itself, sampled a few times
    3. the streaming server's own status page (Icecast, Shoutcast)
    4. the now-playing API of a streaming platform, derived from the host
       (AzuraCast, laut.fm, Radio.co, streamABC)
    5. JSON links on the station's homepage that look like a now-playing API

A method is a small dict saved on the station (see StationStore), e.g.
{"kind": "icy"} or {"kind": "json", "url": ..., "artist": [...], "title": [...]}.
"""
import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp

Track = Dict[str, str]

# Radio France livemeta IDs of the FIP streams, by the part after "fip" in the
# stream URL (icecast.radiofrance.fr/fip<name>-midfi.mp3)
FIP_STATION_IDS = {
    "": 7, "rock": 64, "jazz": 65, "groove": 66, "world": 69, "nouveautes": 70,
    "reggae": 71, "electro": 74, "metal": 77, "pop": 78,
}
RADIO_PARADISE_CHANNELS = ["Main Mix", "Mellow Mix", "Rock Mix", "Global Mix"]

# JSON field names that hold an artist, a title, or both as "Artist - Title"
ARTIST_KEYS = ("artist", "artists", "interpreters", "performer", "performers", "artist_name",
               "artistname", "singer", "author", "authors", "band")
TITLE_KEYS = ("title", "song", "song_title", "songtitle", "track", "track_title", "trackname",
              "track_name", "name")
COMBINED_KEYS = ("streamtitle", "songtitle", "song", "title", "text", "now_playing", "nowplaying",
                 "current", "currentsong", "current_song", "current_track", "track")
# Path words that mark the playing item, or an old or future one
NOW_WORDS = ("now", "current", "playing", "live", "onair", "on_air", "present")
OTHER_WORDS = ("prev", "previous", "history", "last", "next", "upcoming", "played", "recent")

# Homepage links worth trying as a now-playing API
_API_LINK = re.compile(
    r"now.?play|current.?(song|track|title)|on.?air|playlist|livemeta|nowplay|songs?/current|"
    r"metadata|track.?info|/api/", re.I)
_ASSET = re.compile(r"\.(js|css|png|jpe?g|gif|svg|webp|ico|woff2?|ttf|mp3|aac|m3u8?|pls|mp4)(\?|$)", re.I)
_URL_IN_QUOTES = re.compile(r"""["'](\s*(?:https?:)?//[^"'\s<>]+|/[^"'\s<>]*)["']""")


def split_track(text: str) -> Tuple[str, str]:
    """ "Artist - Title" -> (artist, title); without a separator the artist is empty."""
    text = text.strip()
    if " - " in text:
        artist, title = (p.strip() for p in text.split(" - ", 1))
        return artist, title
    return "", text


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def is_station_name(text: str, names: List[str]) -> bool:
    """True when a "title" only repeats the station name (VRT sends "VRT MNM")."""
    t = _norm(text)
    # "VRT MNM" holds the name "MNM" and is no track; "Artist - Title" with the
    # name somewhere inside is a track
    is_track_shaped = " - " in (text or "")
    return not t or any(n and (t in n or (n in t and not is_track_shaped)) for n in map(_norm, names))


def _text(value: Any) -> str:
    """A field value as text: strings, lists of strings, or objects with a name."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return ", ".join(t for t in (_text(v) for v in value) if t)
    if isinstance(value, dict):
        for key in ("name", "title", "text"):
            if isinstance(value.get(key), str):
                return value[key].strip()
    return ""


def get_path(data: Any, path: List[Any]) -> Any:
    for step in path:
        if isinstance(data, dict):
            data = data.get(step)
        elif isinstance(data, list) and isinstance(step, int) and step < len(data):
            data = data[step]
        else:
            return None
    return data


def find_track(data: Any) -> Optional[Dict[str, List[Any]]]:
    """Find where a JSON document keeps the playing track.

    Walks the document breadth first (lists: only the first item, which is the
    newest in feeds). An object with an artist field and a title field, or a
    single "Artist - Title" field, is a candidate. Paths with "now/current"
    words win; paths with "previous/next/history" words lose.
    Returns {"artist": path, "title": path} or {"combined": path}, or None.
    """
    best, best_score = None, None
    queue: List[Tuple[List[Any], Any]] = [([], data)]
    seen = 0
    while queue and seen < 3000:
        path, node = queue.pop(0)
        seen += 1
        if len(path) > 7:
            continue
        if isinstance(node, list):
            if node:
                queue.append((path + [0], node[0]))
            continue
        if not isinstance(node, dict):
            continue

        lower = {k.lower(): k for k in node if isinstance(k, str)}
        artist = next((lower[k] for k in ARTIST_KEYS if k in lower and _text(node[lower[k]])), None)
        title = next((lower[k] for k in TITLE_KEYS
                      if k in lower and lower[k] != artist and _text(node[lower[k]])), None)
        found = None
        if artist and title:
            found = {"artist": path + [artist], "title": path + [title]}
        else:
            combined = next((lower[k] for k in COMBINED_KEYS
                             if k in lower and isinstance(node[lower[k]], str) and " - " in node[lower[k]]), None)
            if combined:
                found = {"combined": path + [combined]}
        if found:
            words = " ".join(str(p).lower() for p in path)
            score = len(path) - 5 * any(w in words for w in NOW_WORDS) + 10 * any(w in words for w in OTHER_WORDS)
            if best_score is None or score < best_score:
                best, best_score = found, score

        for key, value in node.items():
            if isinstance(value, (dict, list)):
                queue.append((path + [key], value))
    return best


def track_from_json(data: Any, method: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """(artist, title) from a JSON document with a found path, or None."""
    if "combined" in method:
        text = _text(get_path(data, method["combined"]))
        artist, title = split_track(text) if text else ("", "")
    else:
        artist = _text(get_path(data, method.get("artist", [])))
        title = _text(get_path(data, method.get("title", [])))
    return (artist, title) if title else None


def builtin_method(stream_url: str) -> Optional[Dict[str, Any]]:
    """The method for a stream of a known provider, from its URL alone."""
    lower = (stream_url or "").lower()
    fip = re.search(r"icecast\.radiofrance\.fr/fip([a-z]*)-", lower)
    if fip and fip.group(1) in FIP_STATION_IDS:
        return {"kind": "provider", "provider": "fip", "id": FIP_STATION_IDS[fip.group(1)]}
    if "kexp" in lower:
        return {"kind": "provider", "provider": "kexp"}
    bbc = re.search(r"(bbc_[a-z0-9_]+)\.m3u8", lower)
    if bbc:
        return {"kind": "provider", "provider": "bbc", "service": bbc.group(1)}
    if lower.endswith("/willy.mp3") and "qmusicbe" in lower:
        return {"kind": "provider", "provider": "willy"}
    if "soma.fm" in lower or "somafm" in lower:
        # Station id = stream file name without extension (groovesalad.pls)
        seg = os.path.splitext(os.path.basename(urlparse(lower).path))[0]
        return {"kind": "provider", "provider": "somafm", "station": seg or "groovesalad"}
    if "radioparadise.com" in lower:
        channel = next((i for i, w in ((1, "mellow"), (2, "rock"), (3, "global")) if w in lower), 0)
        return {"kind": "provider", "provider": "radioparadise", "channel": channel}
    return None


def platform_candidates(stream_url: str) -> List[str]:
    """Now-playing API URLs of streaming platforms, derived from the stream URL."""
    p = urlparse(stream_url)
    host, parts = p.hostname or "", [x for x in p.path.split("/") if x]
    urls = []
    # AzuraCast: https://host/listen/<station>/radio.mp3
    if len(parts) >= 2 and parts[0] == "listen":
        urls.append(f"{p.scheme}://{p.netloc}/api/nowplaying/{parts[1]}")
    # laut.fm: stream.laut.fm/<station> or <station>.stream.laut.fm
    if host.endswith("laut.fm"):
        name = parts[0] if host == "stream.laut.fm" and parts else host.split(".")[0]
        urls.append(f"https://api.laut.fm/station/{name}/current_song")
    # Radio.co: s<N>.radio.co/<station id>/listen
    if host.endswith("radio.co") and parts:
        urls.append(f"https://public.radio.co/stations/{parts[0]}/status")
    # streamABC: <key>-mp3-128 style mount names
    if host.endswith("streamabc.net") and parts:
        key = re.sub(r"-(mp3|aac|ogg|opus)(-\d+)?.*$", "", parts[0])
        urls.append(f"https://api.streamabc.net/metadata/channel/{key}.json")
    return urls


def homepage_links(html: str, base: str, limit: int = 12) -> List[str]:
    """Links on a page that look like a now-playing API, most likely first."""
    links = []
    for raw in _URL_IN_QUOTES.findall(html):
        raw = raw.strip()
        if not _API_LINK.search(raw) or _ASSET.search(raw):
            continue
        url = urljoin(base, raw if not raw.startswith("//") else "https:" + raw)
        if url.startswith("http") and url not in links:
            links.append(url)
    # .json and "now playing" style links first
    links.sort(key=lambda u: (not u.split("?")[0].endswith(".json"), not re.search(r"now|current", u, re.I)))
    return links[:limit]


class TrackInfo:
    """Reads track info for radio streams and detects how to read it."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        # Station names announced by streams via their icy-name header
        self.icy_names: Dict[str, str] = {}

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0 (HSG Canvas)"})
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_json(self, url: str) -> Optional[Any]:
        """GET a JSON document; None on any failure."""
        try:
            async with self._http().get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception as e:
            logging.debug(f"Track info: no JSON from {url}: {e}")
        return None

    async def get_text(self, url: str, limit: int = 512_000) -> Optional[str]:
        try:
            async with self._http().get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return (await resp.content.read(limit)).decode("utf-8", "ignore")
        except Exception as e:
            logging.debug(f"Track info: no page at {url}: {e}")
        return None

    # ── reading ────────────────────────────────────────────────────────

    async def fetch(self, stream_url: str, resolved_url: str, method: Optional[Dict[str, Any]],
                    names: List[str]) -> Optional[Track]:
        """The playing track, with the station's method; ICY is the fallback."""
        method = method or builtin_method(stream_url)
        track = None
        if method and method.get("kind") not in (None, "icy", "none"):
            track = await self.read(method, names)
        return track or await self.read_icy(resolved_url, names)

    async def read(self, method: Dict[str, Any], names: List[str]) -> Optional[Track]:
        kind = method.get("kind")
        try:
            if kind == "provider":
                return await self._read_provider(method)
            if kind == "json":
                data = await self.get_json(method["url"])
                found = track_from_json(data, method) if data is not None else None
            elif kind == "icecast":
                found = await self._read_icecast(method["url"], method.get("mount", ""))
            elif kind == "shoutcast":
                found = self._parse_shoutcast(method["url"], await self.get_text(method["url"], 4096))
            else:
                return None
        except Exception as e:
            logging.debug(f"Track info read failed for {method}: {e}")
            return None
        if not found or is_station_name(found[1], names):
            return None
        artist, title = found
        return {"title": title, "artist": artist, "album": "", "station": names[0] if names else "",
                "source": kind}

    async def read_icy(self, url: str, names: List[str]) -> Optional[Track]:
        """The track from the stream's own ICY metadata, if it sends one."""
        text = await self._icy_title(url)
        if not text or is_station_name(text, names + [self.icy_names.get(url, "")]):
            return None
        artist, title = split_track(text)
        return {"title": title, "artist": artist, "album": "", "station": names[0] if names else "",
                "source": "icy"}

    async def _icy_title(self, url: str, info: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Raw StreamTitle of one ICY block: "" when the stream sends ICY blocks
        but no title now, None when it sends no ICY at all.
        Fills `info` with the response headers."""
        try:
            async with self._http().get(url, timeout=aiohttp.ClientTimeout(total=15),
                                        headers={"Icy-MetaData": "1"}) as resp:
                if info is not None:
                    info.update({"final_url": str(resp.url), "headers": dict(resp.headers)})
                if resp.status not in (200, 206):
                    return None
                name = (resp.headers.get("icy-name") or "").strip()
                if name:
                    self.icy_names[url] = name
                interval = int(resp.headers.get("icy-metaint", 0) or 0)
                if interval <= 0:
                    return None
                # Skip one audio block, then read the length-prefixed metadata block
                await resp.content.readexactly(interval)
                length = (await resp.content.readexactly(1))[0] * 16
                if not length:
                    return ""
                block = (await resp.content.readexactly(length)).decode("utf-8", "ignore")
        except Exception as e:
            logging.debug(f"ICY read failed for {url}: {e}")
            return None
        match = re.search(r"StreamTitle='(.*?)';", block)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _parse_shoutcast(url: str, text: Optional[str]) -> Optional[Tuple[str, str]]:
        """/7.html: "<body>listeners,status,peak,max,unique,bitrate,Artist - Title</body>".
        /currentsong: the plain title. Any other page is not a title."""
        if not text:
            return None
        if url.endswith("/7.html"):
            body = re.search(r"<body>(.*?)</body>", text, re.S | re.I)
            fields = body.group(1).split(",", 6) if body else []
            return split_track(fields[6]) if len(fields) == 7 else None
        text = text.strip()
        if not text or "<" in text or "\n" in text or len(text) > 200:
            return None
        return split_track(text)

    async def _read_icecast(self, status_url: str, mount: str) -> Optional[Tuple[str, str]]:
        data = await self.get_json(status_url)
        sources = (data or {}).get("icestats", {}).get("source", [])
        if isinstance(sources, dict):  # Icecast sends a single mount as an object
            sources = [sources]
        for source in sources:
            if mount and not str(source.get("listenurl", "")).endswith(mount):
                continue
            if source.get("title"):
                if source.get("artist"):
                    return source["artist"], source["title"]
                return split_track(source["title"])
        return None

    async def _read_provider(self, m: Dict[str, Any]) -> Optional[Track]:
        provider = m["provider"]
        if provider == "somafm":
            data = await self.get_json(f"https://somafm.com/songs/{m['station']}.json")
            if data and data.get("songs"):
                s = data["songs"][0]
                return {"title": s.get("title", ""), "artist": s.get("artist", ""), "album": s.get("album", ""),
                        "station": f"SomaFM {m['station'].title()}", "source": "somafm"}
        elif provider == "radioparadise":
            data = await self.get_json(f"https://api.radioparadise.com/api/now_playing?chan={m['channel']}")
            if data and data.get("title"):
                return {"title": data["title"], "artist": data.get("artist", ""),
                        "album": data.get("album", "") + (f" ({data['year']})" if data.get("year") else ""),
                        "station": f"Radio Paradise {RADIO_PARADISE_CHANNELS[m['channel']]}",
                        "source": "radioparadise"}
        elif provider == "fip":
            now = ((await self.get_json(f"https://api.radiofrance.fr/livemeta/live/{m['id']}/fip_extended"))
                   or {}).get("now") or {}
            # Between songs "now" is the presenter ("Le direct") without interpreters
            if now.get("title") and now.get("interpreters"):
                return {"title": now["title"], "artist": now["interpreters"], "album": now.get("album") or "",
                        "station": "FIP", "source": "fip"}
        elif provider == "kexp":
            play = (((await self.get_json("https://api.kexp.org/v2/plays/?limit=1")) or {})
                    .get("results") or [{}])[0]
            # An "airbreak" is the DJ talking: no track
            if play.get("play_type") == "trackplay" and play.get("song"):
                return {"title": play["song"], "artist": play.get("artist") or "",
                        "album": play.get("album") or "", "station": "KEXP", "source": "kexp"}
        elif provider == "bbc":
            data = await self.get_json(f"https://rms.api.bbc.co.uk/v2/services/{m['service']}/segments/latest")
            for segment in (data or {}).get("data") or []:
                if (segment.get("offset") or {}).get("now_playing"):
                    titles = segment.get("titles") or {}
                    return {"title": titles.get("secondary") or "", "artist": titles.get("primary") or "",
                            "album": "", "station": "BBC", "source": "bbc"}
        elif provider == "willy":
            track = (((await self.get_json("https://api.willy.radio/2.4/tracks/plays?limit=1")) or {})
                     .get("played_tracks") or [{}])[0]
            try:
                ends = datetime.fromisoformat(track["played_at"]).timestamp() + track.get("duration", 0)
            except (KeyError, TypeError, ValueError):
                ends = 0
            # The feed lists the last track; after it ends, the DJ or an ad is on
            if track.get("title") and ends + 30 > time.time():
                return {"title": track["title"], "artist": (track.get("artist") or {}).get("name", ""),
                        "album": "", "station": "Willy", "source": "willy"}
        return None

    # ── detection ──────────────────────────────────────────────────────

    async def detect(self, stream_url: str, resolved_url: str, names: List[str],
                     icy_samples: int = 3, icy_gap: float = 6.0) -> Dict[str, Any]:
        """Find a method for this station. Returns the method with a "sample" track."""
        def done(method: Dict[str, Any], track: Optional[Any] = None) -> Dict[str, Any]:
            if isinstance(track, dict):
                track = f"{track.get('artist', '')} - {track.get('title', '')}".strip(" -")
            elif isinstance(track, tuple):
                track = " - ".join(t for t in track if t)
            method.update({"checked": int(time.time()), "sample": track or None})
            logging.info(f"Track info for {names[0] if names else stream_url}: {method['kind']} ({track})")
            return method

        # 1. Known provider
        builtin = builtin_method(stream_url)
        if builtin:
            return done(builtin, await self.read(builtin, names))

        # 2. ICY titles, sampled a few times to skip gaps between songs.
        # Empty titles (ads, gaps) still mean the stream can send titles; a
        # stream that only ever sends its own name (VRT) cannot.
        info: Dict[str, Any] = {}
        icy_empty = icy_name_only = False
        for i in range(icy_samples):
            text = await self._icy_title(resolved_url, info if i == 0 else None)
            if text and not is_station_name(text, names + [self.icy_names.get(resolved_url, "")]):
                return done({"kind": "icy"}, text)
            icy_empty |= text == ""
            icy_name_only |= bool(text)
            if i < icy_samples - 1:
                await asyncio.sleep(icy_gap)

        final = urlparse(info.get("final_url") or resolved_url)
        base = f"{final.scheme}://{final.netloc}"

        # 3. The streaming server's own status pages
        icecast = {"kind": "icecast", "url": f"{base}/status-json.xsl", "mount": final.path}
        found = await self._read_icecast(icecast["url"], icecast["mount"])
        if found and not is_station_name(found[1], names):
            return done(icecast, found)
        for path in ("/currentsong?sid=1", "/7.html"):
            method = {"kind": "shoutcast", "url": base + path}
            track = await self.read(method, names)
            if track:
                return done(method, track)

        # 4. Streaming platform APIs, then 5. links on the station's homepage
        candidates = platform_candidates(resolved_url) + platform_candidates(stream_url)
        headers = {k.lower(): v for k, v in (info.get("headers") or {}).items()}
        homepage = headers.get("icy-url", "").strip()
        if homepage.startswith("http"):
            html = await self.get_text(homepage)
            if html:
                candidates += homepage_links(html, homepage)
        for url in dict.fromkeys(candidates):
            data = await self.get_json(url)
            if data is None:
                continue
            paths = find_track(data)
            if not paths:
                continue
            method = {"kind": "json", "url": url, **paths}
            track = track_from_json(data, method)
            if track and not is_station_name(track[1], names):
                return done(method, track)

        if icy_empty and not icy_name_only:
            return done({"kind": "icy"})
        return done({"kind": "none"})


# A "none" result is tried again after this many seconds
RETRY_NONE_AFTER = 24 * 3600


async def detect_stations(track_info: "TrackInfo", store, resolve_url, only_missing: bool = True,
                          concurrency: int = 3) -> int:
    """Detect the track-info method of the stations in the store, in the background.

    only_missing: skip stations that have a method, except "none" results older
    than a day. resolve_url turns a playlist URL (.pls, .m3u) into the stream.
    Returns the number of stations checked.
    """
    now = time.time()
    todo = [s for s in store.stations() if not only_missing or not s.get("track_info")
            or (s["track_info"].get("kind") == "none"
                and now - s["track_info"].get("checked", 0) > RETRY_NONE_AFTER)]
    sem = asyncio.Semaphore(concurrency)

    async def one(station):
        async with sem:
            try:
                resolved = await resolve_url(station["url"])
                method = await track_info.detect(station["url"], resolved, [station["name"]])
                store.set_track_info(station["url"], method)
            except Exception as e:
                logging.warning(f"Track info detection failed for {station['name']}: {e}")

    await asyncio.gather(*(one(s) for s in todo))
    if todo:
        logging.info(f"Track info: checked {len(todo)} station(s)")
    return len(todo)
