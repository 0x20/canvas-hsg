# Code-quality backlog

Parked from the 2026-05-07 concurrency / crash / perf audit. Tackle in order
of severity within each section. Items marked (2×) were flagged independently
by two different review agents.

## HIGH

- DisplayStack mutates without a lock — `managers/display_stack.py:54-191`
  - Push/pop/remove all read-modify-write `self._stack` and `await` mid-mutation. The new `EXCLUSIVE_TYPES` eviction is racy under concurrent BT/Spotify/Sendspin pushes. Adding `asyncio.Lock` on the public mutators is the highest-leverage single fix on the list.
- WebSocketManager.broadcast iterates a live set — `managers/websocket_manager.py:43-70` (2×)
  - `for ws in self.active_connections:` raises `RuntimeError: Set changed size during iteration` if a client connects/drops mid-broadcast. Snapshot via `list(...)` first.
- Sync subprocesses on async event loop (2×)
  - `managers/hdmi_cec.py:72-117` (Popen.communicate up to 10s)
  - `routes.py:129,140,182,303,318` (pactl/amixer/systemctl)
  - `managers/spotify_manager.py:160` (pactl on every track change)
  - `managers/sendspin_manager.py:55`
  - `managers/chromium_manager.py:261-280` (`_has_zombie_children` nests N×ps)
  - Replace with `asyncio.create_subprocess_exec` or `asyncio.to_thread`.
- Bluetooth poll fights `pause_playback()` — `managers/bluetooth_manager.py:104-195`
  - 3s poll re-pushes BT after Spotify takes over because AVRCP Pause hasn't propagated. Add `_suppress_until` timestamp gate.
- Cross-manager `is_playing` writes unsynchronised — `managers/bluetooth_manager.py:225-228`, `managers/sendspin_manager.py:96-97`
  - Direct external writes to peer managers' state. Replace with explicit `mark_preempted()` methods.
- Bluetooth D-Bus parser is fragile, swallows real bugs — `managers/bluetooth_manager.py:377-526` (2×)
  - Hand-rolled state machine; nested `dict entry` blocks misalign key/value pairs. Errors logged at debug only. Consider `dbus-fast` / `dbus-next`.
- Lifespan startup-failure leaks Chromium / cage / tasks — `main.py:72-346`
  - Partial init re-raises without tearing down what already started. Wrap in try/except that runs the shutdown sequence.
- `/display/navigate` URL unvalidated (security) — `routes.py:1531-1539`
  - Accepts `file:///` and `chrome://...`. Validate with Pydantic `HttpUrl` + scheme allowlist.

## MEDIUM

- Cancelled tasks not awaited on shutdown — `main.py:355-357` and BT/Sendspin/HA/audio
  - `task.cancel()` without `await task` — finally blocks (aiohttp session close, etc.) leak. Pattern: `try: await task except asyncio.CancelledError: pass`.
- Spotify state file write not atomic, restore unvalidated — `managers/spotify_manager.py:366-405`
  - SIGTERM mid-write leaves truncated JSON. Restore doesn't `isinstance` check restored types; a bad type (e.g. `track_info=None`) crashes the next event handler. Use `tmp + os.replace`.
- Bluetooth re-mutes raspotify+sendspin every 3s poll — `managers/bluetooth_manager.py:151-195`
  - Spawns `pactl list sink-inputs` + N mutes per tick. Cache last sink-inputs and only re-issue on change.
- Sendspin metadata poll spawns 2 dbus-send per 5s tick — `managers/sendspin_manager.py:158-274`
  - ListNames + Get Metadata each tick. Cache the resolved MPRIS bus name.
- Raspotify watchdog has no rate-limit, sudo can hang — `main.py:288-336`
  - If raspotify is broken, restart loop fires every 30s forever. Track `last_restart_at`, refuse <5min apart.
- aiohttp.ClientSession recreated per call (2×)
  - `managers/homeassistant_manager.py:180,243,486` (state push every 5s)
  - `managers/spotify_manager.py:297,324`
  - `managers/audio_manager.py:43,55,255`
  - One shared session per manager, created in `initialize()`, closed in `cleanup()`. The HA `_ws_session` field is declared but never assigned — `cleanup()` is a no-op there.
- `handle_browser_status` lets LAN clients desync state (2×) — `managers/audio_manager.py:164-167`
  - WS clients can flip `_is_playing` arbitrarily. Treat browser reports as advisory only, gate on `current_audio_stream`.
- Bluetooth MAC params unvalidated — `routes.py:1417-1447`
  - `address: str` straight into `bluetoothctl remove <address>`. Add MAC regex check.
- Chromium check_health no cooldown / lock — `managers/chromium_manager.py:286-299`
  - check_health calls stop+start_kiosk synchronously; no in-flight lock. Concurrent restarts can race.
- Health check 10-min journalctl runs every tick — `main.py:298-336`
  - Skip when 60s window already saw output; or run the slow query every other tick.
- Image upload writes are sync — `routes.py:444-449`
  - Multi-MB writes block the event loop. Use `asyncio.to_thread`.
- webcast_manager dead code + uncapped screenshot cache — `managers/webcast_manager.py:210-466`
  - Several scroll-loop methods reference uninitialised `self.*` attributes (AttributeError on call). Screenshot cache at `/tmp/webcast_cache/` has no upper bound.
- HA WS listener no backoff — `managers/homeassistant_manager.py:230-317`
  - 10s reconnect with no jitter hammers HA on outage. Exponential backoff capped at 5min.
- QR / uploaded images written to `static/` and never deleted — `managers/image_manager.py:32-101`
  - Slow disk fill on a kiosk. Add expiry sweep.

## LOW

- `broadcast()` awaits per client serially — `managers/websocket_manager.py:43-70`
  - One slow client stalls the others. Switch to `asyncio.gather(..., return_exceptions=True)` once N clients > 2.
- `audio_conflict._find_sink_inputs` `current_index` reset bug — `managers/audio_conflict.py:84-94`
  - Carries over to next block when a sink-input has no `application.process.binary`.
- `_metadata_poll_loop` exits silently on external `is_playing` flip — `managers/sendspin_manager.py:158-167`
  - `while self.is_playing:` — if BT flips it externally, the loop ends without cleanup. Drive cancellation from `_stop_metadata_polling()` only via a private flag.
- Chromecast subprocess discovery at startup unconditional — `managers/output_target_manager.py:122-165`
  - 5s mDNS spawn at boot even if the user never casts. Make lazy on first `/chromecast/discover` call.
- ChromiumManager log file opened in `"w"` mode every start — `managers/chromium_manager.py:103-112`
  - Clobbers history across restarts. Use `"a"` (append).
- JSON `/ws/audio` parse can crash on non-dict — `routes.py:1244-1250`
  - `msg.get(...)` after `json.loads` of an array/string raises AttributeError outside the JSONDecodeError except. Add `isinstance(msg, dict)` guard.

---

## Suggested order

If picking off items piecemeal, the highest leverage triple is:

1. Lock `DisplayStack` (HIGH #1)
2. Snapshot `WebSocketManager.broadcast` connections (HIGH #2)
3. Move sync subprocesses off the event loop (HIGH #3 — at minimum `pactl` from spotify_manager:160 and the CEC routes)

Those three alone resolve or de-fang ~half of the rest of the list.
