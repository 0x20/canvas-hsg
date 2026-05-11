import { useState, useEffect, useRef } from 'react';
import './App.css';
import NowPlaying from './NowPlaying';
import StaticBackground from './StaticBackground';
import ImageDisplay from './ImageDisplay';
import YouTubePlayer from './YouTubePlayer';
import WebsiteFrame from './WebsiteFrame';
import VideoPlayer from './VideoPlayer';
import AudioPlayer from './AudioPlayer';

function App() {
  const [displayItem, setDisplayItem] = useState({ type: 'static', content: {}, id: 'base' });
  const [displayStack, setDisplayStack] = useState([]);
  const [spotifySeen, setSpotifySeen] = useState(false);
  const wsRef = useRef(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:${window.location.port}/ws/display`;

    console.log('App: Connecting to display WebSocket:', wsUrl);
    let ws = null;
    let reconnectTimeout = null;

    function connect() {
      try {
        ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('App: Display WebSocket connected');
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            console.log('App: Received display event:', message);

            if (message.event === 'display_state') {
              setDisplayItem(message.data);
              setDisplayStack(message.data.stack || []);
              if (message.data.type === 'spotify' || message.data.type === 'sendspin' || message.data.type === 'bluetooth') {
                setSpotifySeen(true);
              }
            }
          } catch (error) {
            console.error('App: Failed to parse WebSocket message:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('App: Display WebSocket error:', error);
        };

        ws.onclose = () => {
          console.log('App: Display WebSocket disconnected, reconnecting...');
          wsRef.current = null;
          reconnectTimeout = setTimeout(connect, 2000);
        };

      } catch (error) {
        console.error('App: Failed to create WebSocket:', error);
        reconnectTimeout = setTimeout(connect, 2000);
      }
    }

    connect();

    return () => {
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (ws) ws.close();
    };
  }, []);

  // Reset spotifySeen when static becomes current (spotify was actually removed from stack)
  useEffect(() => {
    if (displayItem.type === 'static') {
      setSpotifySeen(false);
    }
  }, [displayItem.type]);

  const isNowPlayingActive = displayItem.type === 'spotify' || displayItem.type === 'sendspin' || displayItem.type === 'bluetooth';
  const keepNowPlayingMounted = spotifySeen && !isNowPlayingActive && displayItem.type !== 'static';

  // Silent overlays (image / qrcode / website) shouldn't interrupt audio when
  // a YouTube is already playing underneath. Find the most recent YouTube in
  // the stack; if it isn't currently the top item but something silent is,
  // keep the YouTube iframe mounted as a base layer and overlay on top.
  const SILENT_OVERLAY_TYPES = ['image', 'qrcode', 'website'];
  const ytItem = [...displayStack].reverse().find((i) => i?.type === 'youtube');
  const overlayBelowYt = ytItem && displayItem.id !== ytItem.id &&
                         SILENT_OVERLAY_TYPES.includes(displayItem.type);

  const renderItem = (item) => {
    switch (item.type) {
      case 'image':
      case 'qrcode':  return <ImageDisplay item={item} />;
      case 'youtube': return <YouTubePlayer item={item} />;
      case 'website': return <WebsiteFrame item={item} />;
      case 'video':   return <VideoPlayer item={item} />;
      case 'static':
      default:        return <StaticBackground item={item} />;
    }
  };

  const renderLayers = () => {
    if (isNowPlayingActive) return null;
    // Always wrap in .layer-base so the position in the React tree is stable
    // when a silent overlay arrives. If we conditionally added the wrapper
    // only when an overlay was present, the YouTube component's parent would
    // change (fragment child → div child) and React would unmount/remount it,
    // destroying the iframe and briefly cutting audio — the very thing we're
    // trying to prevent.
    const baseItem = overlayBelowYt ? ytItem : displayItem;
    return (
      <>
        <div className="layer-base">{renderItem(baseItem)}</div>
        {overlayBelowYt && (
          <div className="layer-overlay">{renderItem(displayItem)}</div>
        )}
      </>
    );
  };

  return (
    <>
      {(isNowPlayingActive || keepNowPlayingMounted) && <NowPlaying />}
      {renderLayers()}
      <AudioPlayer />
    </>
  );
}

export default App;
