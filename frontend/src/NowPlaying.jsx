import { useState, useEffect, useRef } from 'react';
import QRCode from 'qrcode';
import useWebSocket from './useWebSocket';
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
  const [qrDataUrl, setQrDataUrl] = useState('');
  const [showQr, setShowQr] = useState(false);

  const trackTextRef = useRef(null);
  const artistTextRef = useRef(null);
  const trackContainerRef = useRef(null);
  const artistContainerRef = useRef(null);
  const progressFillRef = useRef(null);

  // Track updates — the server replays the current track on every
  // (re)connect, so a fresh or recovered client shows the same thing as one
  // that's been connected all along.
  useWebSocket('/ws/spotify-events', {
    onMessage: (message) => {
      if (message.event !== 'track_changed') return;

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
    },
  });

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

  // Progress bar is driven entirely by a CSS animation now. Set on track
  // change, the compositor advances scaleX(0) → scaleX(1) in 100 discrete
  // steps over the track's duration, with 0 main-thread work and < 1
  // composite update per second. Replaces the old setInterval/rAF tick
  // which was costing ~5 ms per second — enough to occasionally land
  // mid-frame and push the compositor over budget.
  useEffect(() => {
    const fillEl = progressFillRef.current;
    if (!fillEl) return;
    if (!track.durationMs || !track.startTime) {
      fillEl.style.animation = '';
      fillEl.style.transform = 'scaleX(0)';
      setShowQr(false);
      return;
    }
    setShowQr(track.durationMs <= 10000);

    // If we're loading mid-track (e.g. restored Spotify state), seed the
    // start of the animation by using a negative animation-delay equal to
    // the elapsed time. Compositor jumps straight to the right step.
    const elapsedMs = Math.max(0, Date.now() - track.startTime);
    fillEl.style.animation = '';
    // force reflow so the new animation actually restarts
    void fillEl.offsetWidth;
    fillEl.style.animation =
      `track-progress ${track.durationMs}ms steps(100) -${elapsedMs}ms forwards`;

    // Schedule a single timeout to flip the QR visible at remaining=10s.
    // No setInterval, no rAF — fires once per track.
    const remaining = track.durationMs - elapsedMs;
    if (remaining > 10000) {
      const timer = setTimeout(() => setShowQr(true), remaining - 10000);
      return () => clearTimeout(timer);
    } else {
      setShowQr(true);
    }
  }, [track.durationMs, track.startTime]);

  // Marquee: forward-only loop with a pause each cycle. We measure the
  // *single-copy* text width while .scroll is OFF (no ::after duplicate
  // yet), then compute the per-cycle distance as singleWidth + gap. Once
  // .scroll is added, the ::after sibling appears and the layer becomes
  // 2× wide; the keyframe translates by exactly that distance so the
  // duplicate ends up where the original started — seamless loop.
  // Duration scales with width so scroll speed is constant.
  useEffect(() => {
    const SCROLL_PX_PER_SEC = 320;
    const PAUSE_FRAC = 0.20;
    const TICK_FPS = 30; // Lock visible motion to 30 ticks/sec — regular cadence

    const setupMarquee = (textEl, containerEl) => {
      if (!textEl || !containerEl) return;
      textEl.classList.remove('scroll');
      textEl.style.animation = '';
      const singleWidth = textEl.scrollWidth;
      const containerWidth = containerEl.clientWidth;
      if (singleWidth <= containerWidth) return; // fits — no scroll
      const fontSize = parseFloat(getComputedStyle(textEl).fontSize) || 16;
      const gap = 3 * fontSize;
      const distance = singleWidth + gap;
      const travelSec = distance / SCROLL_PX_PER_SEC;
      const totalSec = travelSec / (1 - PAUSE_FRAC);
      const steps = Math.max(2, Math.round(TICK_FPS * totalSec));
      textEl.style.setProperty('--scroll-offset', `-${distance}px`);
      textEl.style.animation = `scroll-marquee ${totalSec.toFixed(1)}s steps(${steps}) infinite`;
      textEl.classList.add('scroll');
    };

    const checkScrolling = () => {
      requestAnimationFrame(() => {
        setupMarquee(trackTextRef.current, trackContainerRef.current);
        setupMarquee(artistTextRef.current, artistContainerRef.current);
      });
    };

    checkScrolling();
    window.addEventListener('resize', checkScrolling);
    return () => window.removeEventListener('resize', checkScrolling);
  }, [track]);

  return (
    <div className="now-playing">
      {/* Blurred full-screen background. The dark gradient is stacked above
          the album-art URL inside a single background-image so the layer
          is opaque (no opacity:0.6 → no per-frame alpha blend). */}
      {track.albumArtUrl && (
        <div
          className="background-blur"
          style={{ backgroundImage: `linear-gradient(rgba(15,15,26,0.4),rgba(15,15,26,0.4)), url('${track.albumArtUrl}')` }}
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

      {/* Progress bar — width updated via ref + style mutation, no React
          re-render per tick (see useEffect above). scaleX is GPU-composited. */}
      <div className="progress-bar">
        <div className="progress-fill" ref={progressFillRef} />
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
          <div className="album-name" key={track.name}>
            {track.album}
          </div>
        )}
      </div>
    </div>
  );
}
