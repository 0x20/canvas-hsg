import { useEffect, useState } from 'react';
import useWebSocket from './useWebSocket';
import './PairingNotice.css';

/**
 * PairingNotice - the Music Assistant pairing PIN, shown on top of whatever
 * the canvas displays while the Sendspin art client waits for pairing.
 * Music Assistant asks for the PIN in its own UI; the person who enters it
 * usually stands in front of this screen.
 */
export default function PairingNotice() {
  const [pin, setPin] = useState(null);

  useWebSocket('/ws/now-playing', {
    onMessage: (msg) => {
      if (msg.event === 'pairing') setPin(msg.data.pin || null);
    },
  });

  useEffect(() => {
    fetch('/sendspin/status')
      .then((r) => (r.ok ? r.json() : null))
      .then((s) => setPin(s?.pairing_pin || null))
      .catch(() => {});
  }, []);

  if (!pin) return null;
  return (
    <div className="pairing-notice" role="status">
      <span className="pairing-notice-label">Music Assistant pairing PIN</span>
      <span className="pairing-notice-pin">{pin}</span>
    </div>
  );
}
