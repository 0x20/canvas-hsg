import { useEffect, useRef, useState } from 'react';
import './YouTubePlayer.css';

/**
 * Returns true when the browser would block unmuted autoplay. A fresh
 * AudioContext starts 'suspended' until the page has a user gesture; the
 * kiosk Chromium (--autoplay-policy=no-user-gesture-required) and any page
 * the user has already interacted with report 'running'.
 */
function autoplayBlocked() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return false;
    const ctx = new Ctx();
    const blocked = ctx.state === 'suspended';
    ctx.close();
    return blocked;
  } catch {
    return false;
  }
}

/**
 * YouTubePlayer - Fullscreen YouTube video via IFrame API
 * Plays with sound unless the backend marks the item muted. On browsers
 * that block unmuted autoplay, starts muted with a tap-to-unmute overlay.
 */
export default function YouTubePlayer({ item }) {
  const playerRef = useRef(null);
  const containerRef = useRef(null);
  const autoplayCheckRef = useRef(null);
  const [errored, setErrored] = useState(false);
  const [needsUnmute, setNeedsUnmute] = useState(false);

  const videoId = item?.content?.video_id || '';
  const mute = item?.content?.mute || false;
  // Re-pushing the same video bumps pushed_at (the id and video_id stay the
  // same) — keying on it makes a "restart" actually recreate the player.
  const pushedAt = item?.pushed_at || 0;

  // How long the "video unavailable" message stays before falling back.
  const ERROR_DISPLAY_MS = 8000;

  // How long after onReady before deciding unmuted autoplay was blocked.
  const AUTOPLAY_CHECK_MS = 1500;

  useEffect(() => {
    if (!videoId) return;
    setErrored(false);  // a new video clears any prior "unavailable" state
    setNeedsUnmute(false);

    // Load YouTube IFrame API if not already loaded
    if (!window.YT) {
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      document.head.appendChild(tag);
    }

    function createPlayer() {
      // The API's global callback fires once, asynchronously — bail if this
      // instance unmounted or the API isn't actually ready yet.
      if (!containerRef.current || !window.YT || !window.YT.Player) return;
      if (playerRef.current) {
        try { playerRef.current.destroy(); } catch {}
      }

      // If unmuted autoplay would be blocked, don't even try: start muted
      // (always allowed) and show the unmute overlay right away.
      const startMuted = mute || autoplayBlocked();
      if (startMuted && !mute) setNeedsUnmute(true);

      playerRef.current = new window.YT.Player(containerRef.current, {
        videoId: videoId,
        width: '100%',
        height: '100%',
        playerVars: {
          autoplay: 1,
          controls: 0,
          modestbranding: 1,
          rel: 0,
          showinfo: 0,
          iv_load_policy: 3,
          fs: 0,
          disablekb: 1,
          playsinline: 1,
          mute: startMuted ? 1 : 0,
        },
        events: {
          onReady: (e) => {
            if (startMuted) e.target.mute();
            e.target.playVideo();
            if (startMuted) return;
            // Backup for when the AudioContext probe was wrong: if the
            // player is still cued/unstarted after a moment, autoplay was
            // blocked — retry muted and offer the tap-to-unmute overlay.
            autoplayCheckRef.current = setTimeout(() => {
              let state;
              try { state = e.target.getPlayerState(); } catch { return; }
              // -1 = unstarted, 5 = cued: both mean autoplay never kicked in.
              if (state === -1 || state === 5) {
                e.target.mute();
                e.target.playVideo();
                setNeedsUnmute(true);
              }
            }, AUTOPLAY_CHECK_MS);
          },
          onStateChange: (e) => {
            // YT.PlayerState.ENDED === 0
            if (e.data === 0) {
              // Video ended — tell backend to pop from stack
              fetch(`/display/${item.id}`, { method: 'DELETE' }).catch(() => {});
            }
          },
          onError: (e) => {
            // 2 = invalid id, 5 = HTML5 error, 100 = removed/not found,
            // 101/150 = embedding disabled. Show a clear message, then
            // pop from the stack and fall back to the background.
            console.warn(`YouTube playback error ${e.data} for video ${videoId}`);
            try { playerRef.current?.destroy(); } catch {}
            playerRef.current = null;
            setErrored(true);
          },
        },
      });
    }

    if (window.YT && window.YT.Player) {
      createPlayer();
    } else {
      window.onYouTubeIframeAPIReady = createPlayer;
    }

    return () => {
      // Don't let a still-pending API callback fire into an unmounted instance.
      if (window.onYouTubeIframeAPIReady === createPlayer) {
        window.onYouTubeIframeAPIReady = undefined;
      }
      clearTimeout(autoplayCheckRef.current);
      if (playerRef.current) {
        try { playerRef.current.destroy(); } catch {}
        playerRef.current = null;
      }
    };
  }, [videoId, pushedAt]);

  // Apply mute toggles to the live player without reloading the video.
  useEffect(() => {
    const p = playerRef.current;
    if (!p || typeof p.mute !== 'function') return;
    try { mute ? p.mute() : p.unMute(); } catch {}
    if (mute) setNeedsUnmute(false);
  }, [mute]);

  const handleUnmute = () => {
    try { playerRef.current?.unMute(); } catch {}
    setNeedsUnmute(false);
  };

  // Once an error is shown, leave the message up briefly, then pop the
  // item off the stack so the display returns to the background.
  useEffect(() => {
    if (!errored) return;
    const timer = setTimeout(() => {
      fetch(`/display/${item.id}`, { method: 'DELETE' }).catch(() => {});
    }, ERROR_DISPLAY_MS);
    return () => clearTimeout(timer);
  }, [errored, item?.id]);

  return (
    <div className="youtube-player">
      <div ref={containerRef} className="youtube-container" />
      {needsUnmute && !errored && (
        <button className="youtube-unmute" onClick={handleUnmute}>
          <span className="youtube-unmute-icon">🔇</span>
          <span>Tap to unmute</span>
        </button>
      )}
      {errored && (
        <div className="youtube-error">
          <div className="youtube-error-icon">⚠</div>
          <div className="youtube-error-title">Video unavailable</div>
          <div className="youtube-error-subtitle">
            This video can’t be played — it may have been removed or made private.
          </div>
        </div>
      )}
    </div>
  );
}
