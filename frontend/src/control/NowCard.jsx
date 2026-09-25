import { useEffect, useRef, useState } from 'react';
import { api, hostOf, youtubeThumb, youtubeTitle } from './api';
import { Icon } from './icons';

const MUSIC = { spotify: 'Spotify', sendspin: 'Music Assistant', bluetooth: 'Bluetooth', radio: 'Radio' };

/** What the canvas shows now, in the shape the card renders. */
function useShowing(display, track) {
  const item = display || { type: 'static', content: {} };
  const c = item.content || {};
  const ytId = item.type === 'youtube' ? c.video_id : null;
  // The title of the video it was fetched for, so a new video never shows an old title
  const [fetched, setFetched] = useState({ id: null, title: null });
  const videoTitle = fetched.id === ytId ? fetched.title : null;

  useEffect(() => {
    if (ytId) youtubeTitle(c.url || `https://youtu.be/${ytId}`).then((title) => setFetched({ id: ytId, title }));
  }, [ytId, c.url]);

  if (MUSIC[item.type]) {
    return {
      kind: 'music', label: MUSIC[item.type], item,
      title: track?.name || 'Loading…',
      sub: [track?.artists, track?.album].filter(Boolean).join(' · '),
      art: track?.album_art_url || null,
      paused: !!track?.paused,
    };
  }
  switch (item.type) {
    case 'youtube':
      return { kind: 'video', label: 'YouTube', item, title: videoTitle || 'YouTube video',
               sub: c.mute ? 'Muted' : 'With sound', art: ytId ? youtubeThumb(ytId) : null };
    case 'twitch':
      return { kind: 'video', label: 'Twitch', item, title: c.twitch_id, sub: c.kind, art: null };
    case 'video':
      return { kind: 'screen', label: 'Video', item, title: hostOf(c.video_url || ''), sub: c.video_url, art: null };
    case 'website':
      return { kind: 'screen', label: 'Website', item, title: hostOf(c.url || ''), sub: c.url, art: null };
    case 'image':
      return { kind: 'screen', label: 'Image', item, title: 'Image', sub: '', art: c.image_url, contain: true };
    case 'qrcode':
      return { kind: 'screen', label: 'QR code', item, title: c.qr_content, sub: '', art: c.image_url, contain: true };
    default:
      return { kind: 'idle', label: 'Idle screen', item, title: 'Nothing playing',
               sub: 'Pick a station or a video below', art: c.background_url || null, backdrop: true };
  }
}

/** Stop action for what shows, or null when this panel cannot stop it. */
function stopFor(showing) {
  const { item } = showing;
  if (item.type === 'radio') return () => api('POST', '/audio/stop');
  if (showing.kind === 'video') return () => api('DELETE', '/playback/stop');
  if (showing.kind === 'screen') return () => api('DELETE', `/display/${item.id}`);
  return null;
}

function Volume() {
  const [volume, setVolume] = useState(null);
  const pending = useRef(null);

  useEffect(() => {
    api('GET', '/playback/volume').then((d) => setVolume(d.volume)).catch(() => {});
  }, []);

  // Send at most one request per 150 ms while the thumb moves
  const change = (v) => {
    setVolume(v);
    clearTimeout(pending.current);
    pending.current = setTimeout(() => api('PUT', '/playback/volume', { volume: v }).catch(() => {}), 150);
  };

  return (
    <label className="volume">
      <Icon.speaker />
      <span className="sr-only">Speaker volume</span>
      <input type="range" min="0" max="100" value={volume ?? 0} disabled={volume == null}
             style={{ '--fill': `${volume ?? 0}%` }}
             onChange={(e) => change(Number(e.target.value))} />
      <span className="volume-val mono">{volume ?? '–'}</span>
    </label>
  );
}

export default function NowCard({ display, track }) {
  const showing = useShowing(display, track);
  const stop = stopFor(showing);
  const [busy, setBusy] = useState(false);
  // The browser pause of a radio stream sends no event back: remember which
  // item was paused here, so a new stream starts as not paused
  const [pausedKey, setPausedKey] = useState(null);
  const itemKey = `${showing.item.id}:${showing.item.pushed_at}`;
  const paused = showing.paused || (showing.item.type === 'radio' && pausedKey === itemKey);
  const live = showing.kind !== 'idle' && !paused;

  const run = async (fn) => {
    setBusy(true);
    try { await fn(); } catch (e) { console.warn(e); }
    setBusy(false);
  };

  return (
    <section className="now" aria-label="Now on the canvas">
      <div className={`screen kind-${showing.kind}`}>
        {showing.art && !showing.contain && (
          <div className="screen-bg" style={{ backgroundImage: `url("${showing.art}")` }} />
        )}
        <div className="screen-inner">
          <div className={`tally ${live ? 'is-live' : ''}`}>
            <span className="tally-lamp" />
            {paused ? 'Paused' : live ? 'On air' : 'Idle'}
            <span className="tally-src">{showing.label}</span>
          </div>
          <div className="screen-body">
            {showing.art && !showing.backdrop && (
              <img className={`screen-art ${showing.contain ? 'contain' : ''}`} src={showing.art} alt="" />
            )}
            <div className="screen-text">
              <h2 className="screen-title">{showing.title}</h2>
              {showing.sub && <p className="screen-sub">{showing.sub}</p>}
            </div>
          </div>
        </div>
      </div>

      <div className="now-controls">
        {showing.item.type === 'radio' && (
          <button className="btn ghost" disabled={busy}
                  onClick={() => run(async () => { await api('POST', '/audio/pause'); setPausedKey((k) => (k === itemKey ? null : itemKey)); })}>
            {paused ? <Icon.play /> : <Icon.pause />}
            {paused ? 'Resume' : 'Pause'}
          </button>
        )}
        {stop ? (
          <button className="btn stop" disabled={busy} onClick={() => run(stop)}>
            <Icon.stop /> Stop
          </button>
        ) : showing.kind === 'music' ? (
          <p className="now-hint">Control {showing.label} from your phone</p>
        ) : null}
        <Volume />
      </div>
    </section>
  );
}
