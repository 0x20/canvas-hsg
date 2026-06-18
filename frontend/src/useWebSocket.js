import { useEffect, useRef } from 'react';

/**
 * useWebSocket - the single WebSocket client for the canvas app.
 *
 * Every screen (kiosk and remote) gets identical connection behavior:
 * - reconnects forever (a display must never give up and go stale)
 * - reconnects immediately when the tab becomes visible again (phones and
 *   background tabs get their sockets killed silently)
 * - JSON messages go to onMessage; non-JSON frames (pong) are ignored
 *
 * The server hydrates current state on every (re)connect, so simply staying
 * connected is what keeps all screens rendering the same thing.
 *
 * Returns a ref holding the live WebSocket (null while disconnected) for
 * components that also send.
 *
 * Pass `enabled: false` to keep the hook inert (no connection) — used by
 * display-only mirrors that must not open an audio socket.
 */
export default function useWebSocket(path, { onMessage, onOpen, enabled = true } = {}) {
  const wsRef = useRef(null);
  // Live handler refs so the socket effect never needs to re-run when the
  // caller re-renders with new closures.
  const handlersRef = useRef({ onMessage, onOpen });
  handlersRef.current = { onMessage, onOpen };

  useEffect(() => {
    if (!enabled) return;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${path}`;
    const RECONNECT_DELAY = 2000;

    let disposed = false;
    let reconnectTimeout = null;
    let ws = null;

    function connect() {
      if (disposed) return;
      try {
        ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log(`WS ${path}: connected`);
          handlersRef.current.onOpen?.(ws);
        };

        ws.onmessage = (event) => {
          let msg;
          try {
            msg = JSON.parse(event.data);
          } catch {
            return; // pong / non-JSON frame
          }
          handlersRef.current.onMessage?.(msg, ws);
        };

        ws.onerror = () => {};

        ws.onclose = () => {
          wsRef.current = null;
          if (!disposed) {
            console.log(`WS ${path}: disconnected, reconnecting...`);
            reconnectTimeout = setTimeout(connect, RECONNECT_DELAY);
          }
        };
      } catch {
        reconnectTimeout = setTimeout(connect, RECONNECT_DELAY);
      }
    }

    function onVisibilityChange() {
      if (document.visibilityState === 'visible' && !wsRef.current) {
        clearTimeout(reconnectTimeout);
        connect();
      }
    }

    document.addEventListener('visibilitychange', onVisibilityChange);
    connect();

    return () => {
      disposed = true;
      document.removeEventListener('visibilitychange', onVisibilityChange);
      clearTimeout(reconnectTimeout);
      if (ws) ws.close();
      wsRef.current = null;
    };
  }, [path, enabled]);

  return wsRef;
}
