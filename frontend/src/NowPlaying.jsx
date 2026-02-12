import { useState, useEffect, useRef } from 'react';
import './NowPlaying.css';

/**
 * Now Playing - Spotify display with WebSocket updates
 * Shows track info with scrolling text and blurred album art background
 */
export default function NowPlaying() {
  const [track, setTrack] = useState({
    name: 'Waiting for track...',
    artists: 'Play something on Spotify',
    album: '',
    albumArtUrl: null
  });

  const trackTextRef = useRef(null);
  const artistTextRef = useRef(null);
  const trackContainerRef = useRef(null);
  const artistContainerRef = useRef(null);

  // WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Connect to FastAPI WebSocket endpoint
    const wsUrl = `${protocol}//${window.location.hostname}:${window.location.port}/ws/spotify-events`;

    console.log('Connecting to WebSocket:', wsUrl);
    let ws = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    const RECONNECT_DELAY = 2000;

    function connect() {
      try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          console.log('WebSocket connected');
          reconnectAttempts = 0;
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            console.log('Received event:', message.event, message.data);

            if (message.event === 'track_changed') {
              // Format artists: handle arrays or newline-separated strings
              let artists = message.data.artists || 'Unknown Artist';
              if (Array.isArray(artists)) {
                artists = artists.join(', ');
              } else if (typeof artists === 'string') {
                artists = artists.replace(/\n/g, ', ');
              }

              setTrack({
                name: message.data.name || 'Unknown Track',
                artists: artists,
                album: message.data.album || '',
                albumArtUrl: message.data.album_art_url || null
              });
            }
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
        };

        ws.onclose = () => {
          console.log('WebSocket disconnected');
          ws = null;

          if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            console.log(`Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
            setTimeout(connect, RECONNECT_DELAY);
          } else {
            console.error('Max reconnection attempts reached');
          }
        };

      } catch (error) {
        console.error('Failed to create WebSocket connection:', error);
      }
    }

    connect();

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, []);

  // Check if scrolling is needed for text overflow
  useEffect(() => {
    const checkScrolling = () => {
      // Remove scroll class first
      if (trackTextRef.current) {
        trackTextRef.current.classList.remove('scroll');
      }
      if (artistTextRef.current) {
        artistTextRef.current.classList.remove('scroll');
      }

      // Wait for next frame to get accurate measurements
      requestAnimationFrame(() => {
        // Check track name
        if (trackTextRef.current && trackContainerRef.current) {
          if (trackTextRef.current.scrollWidth > trackContainerRef.current.clientWidth) {
            trackTextRef.current.classList.add('scroll');
            console.log('Track name needs scrolling');
          }
        }

        // Check artist name
        if (artistTextRef.current && artistContainerRef.current) {
          if (artistTextRef.current.scrollWidth > artistContainerRef.current.clientWidth) {
            artistTextRef.current.classList.add('scroll');
            console.log('Artist name needs scrolling');
          }
        }
      });
    };

    checkScrolling();

    // Recheck on window resize
    window.addEventListener('resize', checkScrolling);
    return () => window.removeEventListener('resize', checkScrolling);
  }, [track]);

  return (
    <div className="now-playing">
      {/* Blurred background with album art */}
      <div
        className="background"
        style={track.albumArtUrl ? {
          backgroundImage: `url('${track.albumArtUrl}')`,
          opacity: 0.7
        } : {
          backgroundImage: 'none',
          backgroundColor: '#1a1a2e'
        }}
      />

      {/* Content overlay */}
      <div className="content">
        <div className="track-name" ref={trackContainerRef}>
          <div
            className="scrolling-text"
            ref={trackTextRef}
            data-text={track.name}
          >
            {track.name}
          </div>
        </div>

        <div className="artist-name" ref={artistContainerRef}>
          <div
            className="scrolling-text"
            ref={artistTextRef}
            data-text={track.artists}
          >
            {track.artists}
          </div>
        </div>

        {track.album && (
          <div className="album-name" key={`${track.name}-${track.album}`}>
            {track.album}
          </div>
        )}
      </div>
    </div>
  );
}
