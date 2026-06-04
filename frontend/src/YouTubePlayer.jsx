import { useEffect, useRef, useState } from 'react';
import './YouTubePlayer.css';

/**
 * YouTubePlayer - Fullscreen YouTube video via IFrame API
 * Plays with sound unless the backend marks the item muted.
 */
export default function YouTubePlayer({ item }) {
  const playerRef = useRef(null);
  const containerRef = useRef(null);
  const [errored, setErrored] = useState(false);

  const videoId = item?.content?.video_id || '';
  const mute = item?.content?.mute || false;

  // How long the "video unavailable" message stays before falling back.
  const ERROR_DISPLAY_MS = 8000;

  useEffect(() => {
    if (!videoId) return;
    setErrored(false);  // a new video clears any prior "unavailable" state

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
          mute: mute ? 1 : 0,
        },
        events: {
          onReady: (e) => {
            if (mute) e.target.mute();
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
      if (playerRef.current) {
        try { playerRef.current.destroy(); } catch {}
        playerRef.current = null;
      }
    };
  }, [videoId]);

  // Apply mute toggles to the live player without reloading the video.
  useEffect(() => {
    const p = playerRef.current;
    if (!p || typeof p.mute !== 'function') return;
    try { mute ? p.mute() : p.unMute(); } catch {}
  }, [mute]);

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
