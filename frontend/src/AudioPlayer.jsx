import { useEffect, useRef } from 'react';
import { IS_AUDIO_OUTPUT } from './audioOutput';
import useWebSocket from './useWebSocket';

/**
 * AudioPlayer - Invisible component for browser-based audio streaming
 *
 * Replaces the MPV AudioPool. Listens to /ws/audio for commands from the backend.
 * The backend (output target + volume slider) decides what plays and how loud —
 * this component just executes those commands. Supports HLS via hls.js
 * (bundled, loaded on first use).
 * Inert unless this screen is the designated audio output (?audio=1).
 */
export default function AudioPlayer() {
  const audioRef = useRef(null);
  const hlsRef = useRef(null);
  // Bumped on every play/stop command. A slow hls.js load checks it, so it
  // cannot start a stream that a later command already replaced.
  const commandRef = useRef(0);

  const wsRef = useWebSocket('/ws/audio', {
    enabled: IS_AUDIO_OUTPUT,
    onOpen: () => sendStatus(),
    onMessage: (msg) => handleCommand(msg),
  });

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

  function sendEnded() {
    const audio = audioRef.current;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    // A finite clip (e.g. a sound effect) finished playing on its own.
    // Continuous streams (radio) never fire 'ended', so this only signals
    // genuine end-of-clip — letting the backend clear the station-art overlay.
    ws.send(JSON.stringify({ type: 'audio_ended', src: audio?.src || '' }));
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
    const command = commandRef.current;

    const { default: Hls } = await import('hls.js/light');
    if (command !== commandRef.current) return;  // replaced while loading

    if (Hls.isSupported()) {
      const hls = new Hls();
      hlsRef.current = hls;
      hls.loadSource(url);
      hls.attachMedia(audio);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
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

    if (msg.type === 'audio_play' || msg.type === 'audio_stop') {
      commandRef.current += 1;
    }

    switch (msg.type) {
      case 'audio_play': {
        cleanupHls();
        const url = msg.url || '';
        const volume = msg.volume != null ? msg.volume / 100 : audio.volume;
        audio.volume = Math.max(0, Math.min(1, volume));

        if (url.includes('.m3u8')) {
          loadHls(url).catch(e => console.warn('AudioPlayer: HLS load failed:', e));
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

  useEffect(() => {
    if (!IS_AUDIO_OUTPUT) return;  // display-only mirror: never play/report

    // Report when a finite clip finishes so the backend can drop its overlay.
    const audioEl = audioRef.current;
    if (audioEl) audioEl.addEventListener('ended', sendEnded);

    // Periodic status reports
    const statusInterval = setInterval(sendStatus, 5000);

    return () => {
      clearInterval(statusInterval);
      if (audioEl) audioEl.removeEventListener('ended', sendEnded);
      cleanupHls();
      if (audioEl) {
        audioEl.pause();
        audioEl.src = '';
      }
    };
  }, []);

  return <audio ref={audioRef} style={{ display: 'none' }} preload="none" />;
}
