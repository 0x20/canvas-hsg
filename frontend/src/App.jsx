import { useState, useEffect, useRef } from 'react';
import NowPlaying from './NowPlaying';
import StaticBackground from './StaticBackground';
import ImageDisplay from './ImageDisplay';
import YouTubePlayer from './YouTubePlayer';
import WebsiteFrame from './WebsiteFrame';
import VideoPlayer from './VideoPlayer';
import AudioPlayer from './AudioPlayer';

function App() {
  const [displayItem, setDisplayItem] = useState({ type: 'static', content: {}, id: 'base' });
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

  const renderOverlay = () => {
    switch (displayItem.type) {
      case 'spotify':
      case 'sendspin':
      case 'bluetooth':
        return null; // NowPlaying rendered separately below
      case 'image':
      case 'qrcode':
        return <ImageDisplay item={displayItem} />;
      case 'youtube':
        return <YouTubePlayer item={displayItem} />;
      case 'website':
        return <WebsiteFrame item={displayItem} />;
      case 'video':
        return <VideoPlayer item={displayItem} />;
      case 'static':
      default:
        return <StaticBackground item={displayItem} />;
    }
  };

  return (
    <>
      {(isNowPlayingActive || keepNowPlayingMounted) && <NowPlaying />}
      {!isNowPlayingActive && renderOverlay()}
      <AudioPlayer />
    </>
  );
}

export default App;
