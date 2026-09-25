"""
Station Art Cache

Finds a fullscreen-worthy logo for a radio stream and keeps a copy on disk, so
stations that aren't SomaFM (which has a proper logo API) still get real art on
the canvas instead of a station name on a generic backdrop.

Resolution chain — every source contributes *candidate* image URLs, and the
first candidate that downloads into a big enough image wins:

  1. Seed candidates from the caller (curated `image:` in media_sources.yaml,
     SomaFM's channels.json cover) — these stay highest priority.
  2. Radio-Browser `byurl`: exact stream-URL match in the open station database.
  3. Radio-Browser name search, for streams whose URL isn't in the database.
  4. The stream's own ICY `icy-url` header → that page's og:image /
     apple-touch-icon / large `rel=icon`.
  5. The stream host's homepage → the same scrape.

Seed candidates go through the cache too, so the canvas always renders art from
the Pi. That keeps a stream start from waiting on a remote fetch and survives a
station reorganising its logo URLs later.

Small images are rejected rather than upscaled: a 32px favicon blown up to
fullscreen looks worse than the text fallback the canvas already has.
"""
import asyncio
import hashlib
import io
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp

try:
    from PIL import Image
except ImportError:  # Pillow is in requirements.txt; degrade instead of crash
    Image = None

# Radio-Browser asks API users to identify themselves with a real UA string.
USER_AGENT = "HSGCanvas/4.0 (+https://hackerspace.gent)"
RADIO_BROWSER = "https://all.api.radio-browser.info"

# Anything smaller than this on its shortest edge is not worth showing
# fullscreen, so we skip it and let the next candidate (or the text fallback)
# win. 128 admits apple-touch-icons (180px, often the only real logo a station
# publishes) while still rejecting 16/32/64px favicons.
MIN_EDGE = 128
MAX_EDGE = 1024

# Once a candidate is at least this big we stop looking. Candidates are ordered
# most-specific-source first, so this doubles as a tie-break: a 200px logo of
# *this* station beats a 1024px logo of its parent network, which is what you
# get by ranking on size alone (FIP Electro would show the Radio France logo).
GOOD_ENOUGH_EDGE = 200
# Bound on how many candidates we'll download before settling for the best so
# far, so a station with a link-heavy homepage can't stall a stream start.
MAX_CANDIDATES = 12

# Don't re-run the whole chain on every stream start for a station that has no
# art anywhere. Re-check about once a week in case one gets added.
NEGATIVE_TTL = 7 * 24 * 3600

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_HTML_BYTES = 512 * 1024

# Streaming providers that host many unrelated stations. Their homepages carry
# the provider's own branding, so scraping one would give a station the wrong
# logo entirely — skip host-derived homepages for these.
SHARED_STREAM_HOSTS_SUFFIXES = (
    "streamguys1.com", "streamguys.com", "streamtheworld.com", "cdnstream1.com",
    "akamaized.net", "cloudfront.net", "fastly.net", "zeno.fm", "radiojar.com",
    "shoutcast.com", "streamabc.net", "mp3.tb-group.fm", "laut.fm",
)


class StationArtCache:
    """Resolves station logos to locally-cached PNGs served from /station-art."""

    def __init__(self, cache_dir: str, url_prefix: str = "/station-art"):
        self.cache_dir = cache_dir
        self.url_prefix = url_prefix.rstrip("/")
        self.index_path = os.path.join(cache_dir, "index.json")
        self._index: Optional[Dict[str, Any]] = None
        # One lock per station key: two clients starting the same stream at once
        # must not both run the chain and race on the same output file.
        self._locks: Dict[str, asyncio.Lock] = {}

    # ── index ──────────────────────────────────────────────────────────────

    def _load_index(self) -> Dict[str, Any]:
        if self._index is None:
            try:
                with open(self.index_path) as f:
                    self._index = json.load(f)
            except (OSError, ValueError):
                self._index = {}
        return self._index

    def _save_index(self):
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            tmp = f"{self.index_path}.tmp"
            with open(tmp, "w") as f:
                json.dump(self._index or {}, f, indent=2, sort_keys=True)
            os.replace(tmp, self.index_path)
        except OSError as e:
            logging.warning(f"Station art index save failed: {e}")

    @staticmethod
    def _key(stream_url: str) -> str:
        return hashlib.sha1(stream_url.encode("utf-8")).hexdigest()[:16]

    def _public_url(self, entry: Dict[str, Any]) -> str:
        # ?v= busts the browser cache when a refresh replaces the file.
        return f"{self.url_prefix}/{entry['file']}?v={int(entry.get('ts', 0))}"

    # ── public API ─────────────────────────────────────────────────────────

    async def resolve(
        self,
        stream_url: str,
        station_name: Optional[str] = None,
        seed_candidates: Optional[List[str]] = None,
        force: bool = False,
    ) -> Optional[str]:
        """Local URL for this stream's art, resolving and caching it if needed.

        Returns None when no source has a usable image — the caller should then
        fall back to whatever it had (a remote URL, or the canvas text card).
        """
        if not stream_url or Image is None:
            return None

        key = self._key(stream_url)
        index = self._load_index()
        entry = index.get(key)

        if entry and not force:
            if entry.get("file") and os.path.exists(os.path.join(self.cache_dir, entry["file"])):
                return self._public_url(entry)
            if entry.get("miss") and (time.time() - entry.get("ts", 0)) < NEGATIVE_TTL:
                return None

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # Another waiter may have resolved it while we queued on the lock.
            entry = self._load_index().get(key)
            if entry and not force and entry.get("file") and \
                    os.path.exists(os.path.join(self.cache_dir, entry["file"])):
                return self._public_url(entry)
            return await self._resolve_uncached(key, stream_url, station_name, seed_candidates)

    async def _resolve_uncached(
        self, key: str, stream_url: str, station_name: Optional[str],
        seed_candidates: Optional[List[str]],
    ) -> Optional[str]:
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {"User-Agent": USER_AGENT}
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                candidates = await self._gather_candidates(
                    session, stream_url, station_name, seed_candidates
                )
                logging.info(
                    f"Station art: {len(candidates)} candidate(s) for "
                    f"{station_name or stream_url}"
                )
                # Take the *best* candidate, not the first usable one: a station
                # often publishes both a 180px touch icon and a 1000px logo, and
                # ordering by source can't tell which is which. Stop early once
                # something comfortably fills the canvas.
                best = None
                for source, url in candidates[:MAX_CANDIDATES]:
                    img = await self._fetch_image(session, url)
                    if not img:
                        continue
                    if not best or min(img.size) > min(best[0].size):
                        best = (img, source, url)
                    if min(best[0].size) >= GOOD_ENOUGH_EDGE:
                        break

                if best:
                    img, source, url = best
                    meta = await asyncio.to_thread(self._store, img, key, url)
                    if meta:
                        meta.update({
                            "stream_url": stream_url,
                            "name": station_name,
                            "source": source,
                            "remote_url": url,
                            "ts": time.time(),
                        })
                        self._load_index()[key] = meta
                        self._save_index()
                        logging.info(
                            f"Station art cached for {station_name or stream_url}: "
                            f"{meta['width']}x{meta['height']} via {source}"
                        )
                        return self._public_url(meta)
        except Exception as e:
            logging.warning(f"Station art resolution failed for {stream_url}: {e}")
            return None

        # Nothing usable anywhere — remember that so the next stream start is instant.
        self._load_index()[key] = {
            "stream_url": stream_url, "name": station_name,
            "miss": True, "ts": time.time(),
        }
        self._save_index()
        logging.info(f"Station art: no usable image found for {station_name or stream_url}")
        return None

    # ── candidate sources ──────────────────────────────────────────────────

    async def _gather_candidates(
        self, session: aiohttp.ClientSession, stream_url: str,
        station_name: Optional[str], seed: Optional[List[str]],
    ) -> List[tuple]:
        """Ordered (source, url) candidates, deduped, best guess first."""
        out: List[tuple] = []
        seen = set()

        def add(source: str, url: Optional[str]):
            if not url or not isinstance(url, str):
                return
            url = url.strip()
            if not url.startswith(("http://", "https://")) or url in seen:
                return
            # Wikimedia hosts a lot of station logos, but as SVG (which Pillow
            # can't decode) and upload.wikimedia.org 400s our thumbnail requests.
            # Special:FilePath renders any Commons file to PNG at a given width
            # and does serve us, so prefer that rewrite over the original URL.
            rendered = self._wikimedia_png(url)
            if rendered and rendered not in seen:
                seen.add(rendered)
                out.append((f"{source}:wikimedia", rendered))
            seen.add(url)
            out.append((source, url))

        for url in (seed or []):
            add("seed", url)

        for st in await self._radio_browser(session, "byurl", stream_url):
            add("radio-browser:byurl", st.get("favicon"))

        for variant in self._name_variants(station_name):
            for st in await self._radio_browser(session, "byname", variant):
                add("radio-browser:byname", st.get("favicon"))

        # The stream's own ICY headers point at the station homepage.
        homepages: List[str] = []
        icy_url = await self._icy_url(session, stream_url)
        if icy_url:
            homepages.append(icy_url)
        for host in self._homepage_hosts(stream_url):
            homepages.append(f"https://{host}/")

        for page in homepages:
            for url in await self._scrape_page(session, page):
                add(f"page:{urlparse(page).hostname}", url)

        return out

    @staticmethod
    def _homepage_hosts(stream_url: str) -> List[str]:
        """Hosts whose homepage might carry this station's logo.

        The stream host itself, then its parent domain — many stations serve
        audio from `stream.<station>.tld` while the logo lives on `<station>.tld`.
        Streams on shared streaming providers are excluded: walking up from
        `kexp-mp3-128.streamguys1.com` would decorate KEXP with the CDN's logo.
        """
        host = (urlparse(stream_url).hostname or "").lower()
        if not host:
            return []
        parts = host.split(".")
        parent = ".".join(parts[-2:]) if len(parts) > 2 else None
        if any(h and h.endswith(SHARED_STREAM_HOSTS_SUFFIXES) for h in (host, parent)):
            return []
        return [host] + ([parent] if parent and parent != host else [])

    @staticmethod
    async def _read_capped(resp: aiohttp.ClientResponse, cap: int) -> bytes:
        """Read a full response body, stopping at `cap` bytes.

        `resp.content.read(n)` returns *at most* n bytes and happily returns a
        partial body, which silently truncates downloads — decoding one of those
        fails with "image file is truncated". Loop until the stream ends.
        """
        buf = bytearray()
        async for chunk in resp.content.iter_chunked(64 * 1024):
            buf.extend(chunk)
            if len(buf) >= cap:
                break
        return bytes(buf[:cap])

    @staticmethod
    def _name_variants(station_name: Optional[str]) -> List[str]:
        """Search names to try, most specific first.

        Our preset names carry qualifiers the station database doesn't use —
        "BBC Radio 6 Music (320kbps)", "Radio Paradise (Main Mix)", or a
        provider prefix as in "laut.fm Synthwave" — so fall back to a
        progressively plainer name when the exact one finds nothing.
        """
        if not station_name:
            return []
        variants = [station_name]
        plain = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", station_name).strip()
        if plain and plain not in variants:
            variants.append(plain)
        # Drop a leading provider token like "laut.fm " or "181.FM ".
        stripped = re.sub(r"^\S+\.(fm|com|net|one)\s+", "", plain, flags=re.I).strip()
        if stripped and stripped not in variants:
            variants.append(stripped)
        return variants

    @staticmethod
    def _wikimedia_png(url: str) -> Optional[str]:
        """Rewrite an upload.wikimedia.org file URL to a rendered PNG we can fetch.

        Direct thumbnail URLs under upload.wikimedia.org return 400 for us, but
        commons.wikimedia.org/wiki/Special:FilePath/<file>?width=N renders any
        Commons file — including SVG — to PNG and serves it normally.
        """
        if "upload.wikimedia.org" not in url:
            return None
        parts = [p for p in urlparse(url).path.split("/") if p]
        if "thumb" in parts:
            # …/thumb/a/ab/Name.svg/512px-Name.svg.png → the original is Name.svg
            filename = parts[parts.index("thumb") + 3] if len(parts) > parts.index("thumb") + 3 else None
        else:
            filename = parts[-1] if parts else None
        if not filename:
            return None
        return (
            f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"
            f"?width={MAX_EDGE}"
        )

    async def _radio_browser(
        self, session: aiohttp.ClientSession, mode: str, value: str
    ) -> List[Dict[str, Any]]:
        """Query the open Radio-Browser station database. Never raises."""
        try:
            if mode == "byurl":
                async with session.post(
                    f"{RADIO_BROWSER}/json/stations/byurl", data={"url": value}
                ) as resp:
                    if resp.status != 200:
                        return []
                    return await resp.json(content_type=None) or []
            params = {
                "name": value, "limit": "8", "order": "votes",
                "reverse": "true", "hidebroken": "true",
            }
            async with session.get(
                f"{RADIO_BROWSER}/json/stations/search", params=params
            ) as resp:
                if resp.status != 200:
                    return []
                return await resp.json(content_type=None) or []
        except Exception as e:
            logging.debug(f"Radio-Browser {mode} lookup failed for {value}: {e}")
            return []

    async def _icy_url(self, session: aiohttp.ClientSession, stream_url: str) -> Optional[str]:
        """The station homepage advertised in the stream's icy-url header."""
        try:
            async with session.get(
                stream_url, headers={"Icy-MetaData": "1", "Range": "bytes=0-1"}
            ) as resp:
                url = resp.headers.get("icy-url") or resp.headers.get("Icy-Url")
                resp.close()
            if url and url.strip().startswith(("http://", "https://")):
                return url.strip()
        except Exception as e:
            logging.debug(f"ICY header probe failed for {stream_url}: {e}")
        return None

    async def _scrape_page(self, session: aiohttp.ClientSession, page_url: str) -> List[str]:
        """Logo-ish image URLs from a station homepage, biggest/best first."""
        try:
            async with session.get(page_url) as resp:
                if resp.status != 200:
                    return []
                html = (await self._read_capped(resp, MAX_HTML_BYTES)).decode("utf-8", "ignore")
                base = str(resp.url)
        except Exception as e:
            logging.debug(f"Homepage fetch failed for {page_url}: {e}")
            return []

        found: List[str] = []

        # og:image / twitter:image are the station's own share art — usually the
        # largest and most deliberate image on the page.
        for prop in ("og:image", "twitter:image", "twitter:image:src"):
            for m in re.finditer(
                rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]*>', html, re.I
            ):
                c = re.search(r'content=["\']([^"\']+)["\']', m.group(0), re.I)
                if c:
                    found.append(urljoin(base, c.group(1)))

        # Icon links, largest declared `sizes` first; unsized last.
        icons = []
        for m in re.finditer(r"<link[^>]+>", html, re.I):
            tag = m.group(0)
            rel = re.search(r'rel=["\']([^"\']+)["\']', tag, re.I)
            href = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
            if not rel or not href or "icon" not in rel.group(1).lower():
                continue
            sizes = re.search(r'sizes=["\'](\d+)x\d+["\']', tag, re.I)
            icons.append((int(sizes.group(1)) if sizes else 0, urljoin(base, href.group(1))))
        found.extend(url for _, url in sorted(icons, key=lambda t: -t[0]))

        # A web-app manifest usually lists the biggest icons a site publishes
        # (192/512px PWA icons), which beat anything in the page <head>.
        man = re.search(
            r'<link[^>]+rel=["\']manifest["\'][^>]*href=["\']([^"\']+)["\']', html, re.I
        ) or re.search(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']manifest["\']', html, re.I
        )
        if man:
            found.extend(await self._scrape_manifest(session, urljoin(base, man.group(1))))

        return found

    async def _scrape_manifest(self, session: aiohttp.ClientSession, url: str) -> List[str]:
        """Icon URLs from a web app manifest, largest declared size first."""
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return []
                data = json.loads((await self._read_capped(resp, MAX_HTML_BYTES)).decode("utf-8", "ignore"))
                base = str(resp.url)
        except Exception as e:
            logging.debug(f"Manifest fetch failed for {url}: {e}")
            return []

        sized = []
        for icon in (data.get("icons") or []):
            src = icon.get("src")
            if not src:
                continue
            edge = 0
            for token in str(icon.get("sizes", "")).split():
                m = re.match(r"(\d+)x\d+", token)
                if m:
                    edge = max(edge, int(m.group(1)))
            sized.append((edge, urljoin(base, src)))
        return [u for _, u in sorted(sized, key=lambda t: -t[0])]

    # ── download & validate ────────────────────────────────────────────────

    async def _fetch_image(self, session: aiohttp.ClientSession, url: str):
        """Download and decode one candidate, or None if it isn't usable art."""
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                raw = await self._read_capped(resp, MAX_IMAGE_BYTES)
        except Exception as e:
            logging.debug(f"Station art download failed for {url}: {e}")
            return None

        if not raw:
            return None

        # Decoding a large image takes long on a Pi: keep it off the event loop.
        img = await asyncio.to_thread(self._decode, raw)
        if img is None:
            # SVG, HTML error page, or anything else Pillow can't decode.
            logging.debug(f"Station art candidate is not a decodable image: {url}")
            return None

        if min(img.size) < MIN_EDGE:
            logging.debug(f"Station art candidate too small ({img.size}): {url}")
            return None
        return img

    @staticmethod
    def _decode(raw: bytes):
        try:
            img = Image.open(io.BytesIO(raw))
            img.load()
            return img
        except Exception:
            return None

    def _store(self, img, key: str, url: str) -> Optional[Dict[str, Any]]:
        """Normalise a chosen image and write it into the cache as PNG."""
        # Flatten transparency onto black: the canvas shows art on a dark
        # backdrop, and a white-on-transparent logo would otherwise vanish.
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            flat = Image.new("RGB", img.size, (0, 0, 0))
            flat.paste(img, mask=img.split()[-1])
            img = flat
        else:
            img = img.convert("RGB")

        if max(img.size) > MAX_EDGE:
            img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

        filename = f"{key}.png"
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            img.save(os.path.join(self.cache_dir, filename), "PNG", optimize=True)
        except OSError as e:
            logging.warning(f"Station art save failed for {url}: {e}")
            return None

        return {"file": filename, "width": img.size[0], "height": img.size[1]}

    # ── maintenance ────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        index = self._load_index()
        cached = [e for e in index.values() if e.get("file")]
        return {
            "cache_dir": self.cache_dir,
            "cached": len(cached),
            "misses": sum(1 for e in index.values() if e.get("miss")),
            "entries": sorted(
                (
                    {
                        "name": e.get("name"),
                        "stream_url": e.get("stream_url"),
                        "source": e.get("source"),
                        "size": f"{e.get('width')}x{e.get('height')}" if e.get("file") else None,
                        "cached": bool(e.get("file")),
                        "art_url": self._public_url(e) if e.get("file") else None,
                    }
                    for e in index.values()
                ),
                key=lambda e: (not e["cached"], (e["name"] or "").lower()),
            ),
        }

    def clear(self, stream_url: Optional[str] = None) -> int:
        """Drop cached art (one stream, or all). Returns entries removed."""
        index = self._load_index()
        keys = [self._key(stream_url)] if stream_url else list(index)
        removed = 0
        for key in keys:
            entry = index.pop(key, None)
            if not entry:
                continue
            removed += 1
            if entry.get("file"):
                try:
                    os.remove(os.path.join(self.cache_dir, entry["file"]))
                except OSError:
                    pass
        self._save_index()
        return removed
