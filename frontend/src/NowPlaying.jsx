import { useState, useEffect, useRef } from 'react';
import QRCode from 'qrcode';
import './NowPlaying.css';

/**
 * Now Playing - Spotify display with WebSocket updates
 * Shows track info with blurred album art background and centered cover
 */
export default function NowPlaying() {
  const [track, setTrack] = useState({
    name: 'Waiting for track...',
    artists: 'Play something on Spotify',
    album: '',
    albumArtUrl: null,
    durationMs: 0,
    startTime: null,
    spotifyUrl: null
  });
  const [progress, setProgress] = useState(0);
  const [qrDataUrl, setQrDataUrl] = useState('');
  const [showQr, setShowQr] = useState(false);

  const trackTextRef = useRef(null);
  const artistTextRef = useRef(null);
  const trackContainerRef = useRef(null);
  const artistContainerRef = useRef(null);

  // WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
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
              let artists = message.data.artists || 'Unknown Artist';
              if (Array.isArray(artists)) {
                artists = artists.join(', ');
              } else if (typeof artists === 'string') {
                artists = artists.replace(/\n/g, ', ');
              }

              console.log('Track data received:', message.data);
              setTrack({
                name: message.data.name || 'Unknown Track',
                artists: artists,
                album: message.data.album || '',
                albumArtUrl: message.data.album_art_url || null,
                durationMs: message.data.duration_ms || 0,
                startTime: Date.now(),
                spotifyUrl: message.data.spotify_url || null
              });
              console.log('Spotify URL:', message.data.spotify_url);
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

  // Generate QR code as data URL string (no canvas intermediary)
  // Skip QR generation entirely if no URL (e.g. Sendspin tracks)
  useEffect(() => {
    if (!track.spotifyUrl) {
      setQrDataUrl('');
      return;
    }
    const url = track.spotifyUrl;

    const genQR = (lightColor) => {
      QRCode.toDataURL(url, {
        width: 58,
        margin: 0,
        errorCorrectionLevel: 'L',
        color: { dark: '#000000', light: lightColor }
      }).then(dataUrl => setQrDataUrl(dataUrl));
    };

    if (!track.albumArtUrl) {
      genQR('#ffffff');
      return;
    }

    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = 16;
      c.height = 16;
      const ctx = c.getContext('2d');
      ctx.drawImage(img, 0, 0, 16, 16);
      const data = ctx.getImageData(0, 0, 16, 16).data;
      let bestColor = [255, 255, 255];
      let bestScore = 0;
      for (let i = 0; i < data.length; i += 4) {
        const r = data[i], g = data[i+1], b = data[i+2];
        const max = Math.max(r, g, b), min = Math.min(r, g, b);
        const sat = max === 0 ? 0 : (max - min) / max;
        const bri = (r + g + b) / 3;
        const score = sat * 2 + (bri > 100 ? 1 : 0);
        if (score > bestScore) {
          bestScore = score;
          bestColor = [r, g, b];
        }
      }
      genQR(`#${bestColor.map(v => v.toString(16).padStart(2, '0')).join('')}`);
    };
    img.src = track.albumArtUrl;
  }, [track.albumArtUrl, track.spotifyUrl]);

  // Update progress bar and QR code visibility
  useEffect(() => {
    if (!track.durationMs || !track.startTime) {
      setProgress(0);
      setShowQr(false);
      return;
    }

    // Show QR immediately if song is shorter than 10s
    if (track.durationMs <= 10000) {
      setShowQr(true);
    } else {
      setShowQr(false);
    }

    const interval = setInterval(() => {
      const elapsed = Date.now() - track.startTime;
      const remaining = track.durationMs - elapsed;
      const progressPercent = Math.min((elapsed / track.durationMs) * 100, 100);
      setProgress(progressPercent);
      if (remaining <= 10000) {
        setShowQr(true);
      }
    }, 100);

    return () => clearInterval(interval);
  }, [track.durationMs, track.startTime]);

  // Check if scrolling is needed for text overflow
  useEffect(() => {
    const checkScrolling = () => {
      if (trackTextRef.current) {
        trackTextRef.current.classList.remove('scroll');
      }
      if (artistTextRef.current) {
        artistTextRef.current.classList.remove('scroll');
      }

      requestAnimationFrame(() => {
        if (trackTextRef.current && trackContainerRef.current) {
          const overflow = trackTextRef.current.scrollWidth - trackContainerRef.current.clientWidth;
          if (overflow > 0) {
            trackTextRef.current.style.setProperty('--scroll-offset', `-${overflow}px`);
            trackTextRef.current.classList.add('scroll');
          }
        }

        if (artistTextRef.current && artistContainerRef.current) {
          const overflow = artistTextRef.current.scrollWidth - artistContainerRef.current.clientWidth;
          if (overflow > 0) {
            artistTextRef.current.style.setProperty('--scroll-offset', `-${overflow}px`);
            artistTextRef.current.classList.add('scroll');
          }
        }
      });
    };

    checkScrolling();

    window.addEventListener('resize', checkScrolling);
    return () => window.removeEventListener('resize', checkScrolling);
  }, [track]);

  return (
    <div className="now-playing">
      {/* Blurred full-screen background */}
      {track.albumArtUrl && (
        <div
          className="background-blur"
          style={{ backgroundImage: `url('${track.albumArtUrl}')` }}
        />
      )}

      {/* Centered sharp album art */}
      <div className="cover-wrapper">
        {track.albumArtUrl ? (
          <img
            className="cover-art"
            src={track.albumArtUrl}
            alt=""
          />
        ) : (
          <svg className="cover-art-fallback" viewBox="0 0 24 24" fill="white">
            <path d="M17.71 7.71L12 2h-1v7.59L6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l5.71-5.71-4.3-4.29 4.3-4.29zM13 5.83l1.88 1.88L13 9.59V5.83zm1.88 10.46L13 18.17v-3.76l1.88 1.88z"/>
          </svg>
        )}
      </div>

      {/* Progress bar */}
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      {/* Spotify QR Code - fades in for last 10s of song */}
      {qrDataUrl && (
        <img className={`qr-code${showQr ? ' qr-visible' : ''}`} src={qrDataUrl} width="58" height="58" alt="" />
      )}

      {/* Content overlay */}
      <div className="content">
        <div className="track-name" ref={trackContainerRef}>
          <div
            className="scrolling-text"
            ref={trackTextRef}
          >
            {track.name}
          </div>
        </div>

        <div className="artist-name" ref={artistContainerRef}>
          <div
            className="scrolling-text"
            ref={artistTextRef}
          >
            {track.artists}
          </div>
        </div>

        {track.album && (
          <div className="album-name" key={track.name}>
            {track.album}
          </div>
        )}
      </div>
    </div>
  );
}
