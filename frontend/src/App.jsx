import { useState, useEffect } from 'react';
import NowPlaying from './NowPlaying';
import StaticBackground from './StaticBackground';

function App() {
  const [currentView, setCurrentView] = useState('static');
  const [spotifyState, setSpotifyState] = useState('stopped');

  // WebSocket connection to listen for Spotify state changes
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:${window.location.port}/ws/spotify-state`;

    console.log('App: Connecting to WebSocket:', wsUrl);
    let ws = null;

    function connect() {
      try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          console.log('App: WebSocket connected for state changes');
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            console.log('App: Received state event:', message);

            if (message.event === 'spotify_state') {
              const isPlaying = message.data.is_playing;
              setSpotifyState(isPlaying ? 'playing' : 'stopped');
              setCurrentView(isPlaying ? 'now-playing' : 'static');
            }
          } catch (error) {
            console.error('App: Failed to parse WebSocket message:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('App: WebSocket error:', error);
        };

        ws.onclose = () => {
          console.log('App: WebSocket disconnected, reconnecting...');
          setTimeout(connect, 2000);
        };

      } catch (error) {
        console.error('App: Failed to create WebSocket:', error);
      }
    }

    connect();

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, []);

  return currentView === 'now-playing' ? <NowPlaying /> : <StaticBackground />;
}

export default App;
