import { useEffect, useRef, useState } from 'react';
import './YouTubePlayer.css';

/**
 * YouTubePlayer - Fullscreen YouTube video via IFrame API
 * Audio only plays on kiosk (localhost), muted on remote mirrors.
 */
export default function YouTubePlayer({ item }) {
  const playerRef = useRef(null);
  const containerRef = useRef(null);
  const [ready, setReady] = useState(false);

  const videoId = item?.content?.video_id || '';
  const isKiosk = typeof window !== 'undefined' &&
    (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost');

  useEffect(() => {
    if (!videoId) return;

    // Load YouTube IFrame API if not already loaded
    if (!window.YT) {
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      document.head.appendChild(tag);
    }

    function createPlayer() {
      if (playerRef.current) {
        playerRef.current.destroy();
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
          mute: isKiosk ? 0 : 1,
        },
        events: {
          onReady: (e) => {
            setReady(true);
            if (!isKiosk) {
              e.target.mute();
            }
          },
          onStateChange: (e) => {
            // YT.PlayerState.ENDED === 0
            if (e.data === 0) {
              // Video ended — tell backend to pop from stack
              fetch(`/display/${item.id}`, { method: 'DELETE' }).catch(() => {});
            }
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
      if (playerRef.current) {
        try { playerRef.current.destroy(); } catch {}
        playerRef.current = null;
      }
    };
  }, [videoId]);

  return (
    <div className="youtube-player">
      <div ref={containerRef} className="youtube-container" />
    </div>
  );
}
