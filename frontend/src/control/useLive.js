import { useEffect, useState } from 'react';
import useWebSocket from '../useWebSocket';
import { api } from './api';

/**
 * Live server state for the control panel.
 *
 * - display: the display stack's top item and the full stack (/ws/display)
 * - track:   the now-playing card data of Spotify, Sendspin, Bluetooth or
 *            radio (/ws/now-playing)
 * - pin:     the Music Assistant pairing PIN while pairing waits
 * - online:  true while the display socket is connected
 */
export default function useLive() {
  const [display, setDisplay] = useState(null);
  const [track, setTrack] = useState(null);
  const [pin, setPin] = useState(null);
  const [online, setOnline] = useState(false);

  const displayWs = useWebSocket('/ws/display', {
    onOpen: () => setOnline(true),
    onMessage: (msg) => {
      if (msg.event === 'display_state') setDisplay(msg.data);
    },
  });

  useWebSocket('/ws/now-playing', {
    onMessage: (msg) => {
      if (msg.event === 'track_changed') setTrack(msg.data);
      else if (msg.event === 'playback_state') setTrack((t) => (t ? { ...t, paused: !!msg.data.paused } : t));
      else if (msg.event === 'pairing') setPin(msg.data.pin || null);
    },
  });

  // The socket hook has no close callback: poll its ref for the connection state.
  useEffect(() => {
    const id = setInterval(() => setOnline(displayWs.current?.readyState === WebSocket.OPEN), 2000);
    return () => clearInterval(id);
  }, [displayWs]);

  // A PIN that was requested before this page opened
  useEffect(() => {
    api('GET', '/sendspin/status').then((s) => setPin(s.pairing_pin || null)).catch(() => {});
  }, []);

  return { display, track, pin, online };
}
