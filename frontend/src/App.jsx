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

  const renderDisplay = () => {
    switch (displayItem.type) {
      case 'spotify':
        return <NowPlaying />;
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
      {renderDisplay()}
      <AudioPlayer />
    </>
  );
}

export default App;
