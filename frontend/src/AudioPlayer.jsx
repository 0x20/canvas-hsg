import { useEffect, useRef } from 'react';

/**
 * AudioPlayer - Invisible component for browser-based audio streaming
 *
 * Replaces the MPV AudioPool. Listens to /ws/audio for commands from the backend.
 * Only plays audio on the kiosk (localhost) — remote mirrors stay silent.
 * Supports HLS streams via dynamically loaded hls.js.
 */
export default function AudioPlayer() {
  const audioRef = useRef(null);
  const hlsRef = useRef(null);
  const wsRef = useRef(null);
  const isKiosk = typeof window !== 'undefined' &&
    (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost');

  useEffect(() => {
    // Only the kiosk plays audio
    if (!isKiosk) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:${window.location.port}/ws/audio`;

    let reconnectTimeout = null;

    function sendStatus() {
      const audio = audioRef.current;
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || !audio) return;
      ws.send(JSON.stringify({
        type: 'audio_status',
        playing: !audio.paused && audio.src !== '',
        src: audio.src || '',
        paused: audio.paused,
        volume: Math.round(audio.volume * 100),
      }));
    }

    function cleanupHls() {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    }

    async function loadHls(url) {
      cleanupHls();
      const audio = audioRef.current;
      if (!audio) return;

      // Dynamic import of hls.js from CDN
      if (!window.Hls) {
        await new Promise((resolve, reject) => {
          const script = document.createElement('script');
          script.src = 'https://cdn.jsdelivr.net/npm/hls.js@latest/dist/hls.min.js';
          script.onload = resolve;
          script.onerror = reject;
          document.head.appendChild(script);
        });
      }

      if (window.Hls && window.Hls.isSupported()) {
        const hls = new window.Hls();
        hlsRef.current = hls;
        hls.loadSource(url);
        hls.attachMedia(audio);
        hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
          audio.play().catch(e => console.warn('AudioPlayer: autoplay blocked:', e));
        });
      } else {
        // Fallback: try native HLS (Safari)
        audio.src = url;
        audio.play().catch(e => console.warn('AudioPlayer: autoplay blocked:', e));
      }
    }

    function handleCommand(msg) {
      const audio = audioRef.current;
      if (!audio) return;

      switch (msg.type) {
        case 'audio_play': {
          cleanupHls();
          const url = msg.url || '';
          const volume = msg.volume != null ? msg.volume / 100 : audio.volume;
          audio.volume = Math.max(0, Math.min(1, volume));

          if (url.includes('.m3u8')) {
            loadHls(url);
          } else {
            audio.src = url;
            audio.play().catch(e => console.warn('AudioPlayer: autoplay blocked:', e));
          }
          break;
        }
        case 'audio_stop':
          cleanupHls();
          audio.pause();
          audio.src = '';
          audio.load();
          break;
        case 'audio_volume':
          if (msg.volume != null) {
            audio.volume = Math.max(0, Math.min(1, msg.volume / 100));
          }
          break;
        case 'audio_pause':
          if (audio.paused) {
            audio.play().catch(() => {});
          } else {
            audio.pause();
          }
          break;
        default:
          console.log('AudioPlayer: unknown command', msg.type);
      }

      // Send status after handling command
      setTimeout(sendStatus, 200);
    }

    function connect() {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('AudioPlayer: WebSocket connected');
          sendStatus();
        };

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data);
            handleCommand(msg);
          } catch (e) {
            console.error('AudioPlayer: parse error:', e);
          }
        };

        ws.onclose = () => {
          console.log('AudioPlayer: WebSocket disconnected, reconnecting...');
          wsRef.current = null;
          reconnectTimeout = setTimeout(connect, 2000);
        };

        ws.onerror = () => {};

      } catch (error) {
        reconnectTimeout = setTimeout(connect, 2000);
      }
    }

    connect();

    // Periodic status reports
    const statusInterval = setInterval(sendStatus, 5000);

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      clearInterval(statusInterval);
      cleanupHls();
      if (wsRef.current) wsRef.current.close();
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current.src = '';
      }
    };
  }, [isKiosk]);

  if (!isKiosk) return null;

  return <audio ref={audioRef} style={{ display: 'none' }} preload="none" />;
}
