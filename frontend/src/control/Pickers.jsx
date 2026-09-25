import { useEffect, useMemo, useState } from 'react';
import { api, somafmLogo, youtubeId, youtubeThumb } from './api';
import { Icon } from './icons';

const groupName = (key) => key.replace(/_/g, ' ');

/** Runs an action, shows it busy, and returns the error text if it fails. */
function useAction() {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const run = async (key, fn) => {
    setBusy(key);
    setError(null);
    try { await fn(); } catch (e) { setError(e.message); }
    setBusy(null);
  };
  return { busy, error, run };
}

// A stable hue per station name, so a tile without a logo still has its own colour
const hueOf = (name) => [...name].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) % 360, 7);

function Monogram({ name }) {
  const letters = name.replace(/[^A-Za-z0-9 ]/g, '').split(' ').filter(Boolean).slice(0, 2).map((w) => w[0]).join('');
  return (
    <span className="monogram" aria-hidden="true" style={{ '--hue': hueOf(name) }}>
      {letters || '♪'}
    </span>
  );
}

function VideoThumb({ id }) {
  const [failed, setFailed] = useState(false);
  if (!id || failed) return null;
  return <img src={youtubeThumb(id)} alt="" loading="lazy" onError={() => setFailed(true)} />;
}

function StationArt({ src, name }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return <Monogram name={name} />;
  return <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />;
}

// ── Radio ───────────────────────────────────────────────────────────────

export function RadioPicker({ stations, display, onEdit }) {
  const [art, setArt] = useState({});
  const [current, setCurrent] = useState(null);
  const [url, setUrl] = useState('');
  const { busy, error, run } = useAction();

  // The server looks up logos in the background: re-read the list now and then
  useEffect(() => {
    const load = () => api('GET', '/audio/station-art').then((s) => {
      setArt(Object.fromEntries((s.entries || []).filter((e) => e.art_url).map((e) => [e.stream_url, e.art_url])));
    }).catch(() => {});
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, []);

  // Which station plays: re-read whenever the canvas changes
  useEffect(() => {
    api('GET', '/audio/status').then((s) => setCurrent(s.current_stream || null)).catch(() => {});
  }, [display]);

  const play = (streamUrl) => run(streamUrl, () => api('POST', '/audio/start', { stream_url: streamUrl }));

  return (
    <div className="picker">
      {(stations?.groups || []).map((group) => (
        <section key={group.name} className="group">
          <h3 className="group-title">{group.name}</h3>
          <div className="tiles">
            {group.stations.map((s) => {
              const on = current === s.url && display?.type === 'radio';
              return (
                <button key={s.url} className={`tile ${on ? 'is-on' : ''}`} title={s.description || s.name}
                        disabled={busy === s.url} onClick={() => play(s.url)}>
                  <span className="tile-art">
                    <StationArt src={art[s.url] || s.image || somafmLogo(s.url)} name={s.name} />
                    {on && <span className="eq" aria-hidden="true"><i /><i /><i /></span>}
                  </span>
                  <span className="tile-name">{s.name}</span>
                </button>
              );
            })}
          </div>
        </section>
      ))}

      <form className="url-row" onSubmit={(e) => { e.preventDefault(); if (url) play(url); }}>
        <input className="input mono" type="url" placeholder="Stream URL (mp3, aac, pls, m3u8)"
               value={url} onChange={(e) => setUrl(e.target.value)} />
        <button className="btn primary" disabled={!url || busy}><Icon.play /> Play</button>
      </form>
      {error && <p className="error">{error}</p>}
      <button className="btn ghost edit-link" onClick={onEdit}><Icon.edit /> Edit stations</button>
    </div>
  );
}

// ── Video ───────────────────────────────────────────────────────────────

export function VideoPicker({ sources, display }) {
  const [url, setUrl] = useState('');
  const [sound, setSound] = useState(true);
  const [query, setQuery] = useState('');
  const { busy, error, run } = useAction();

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    return Object.entries(sources.youtube_channels || {})
      .map(([group, videos]) => [group, (videos || []).filter((v) => !q || v.name.toLowerCase().includes(q))])
      .filter(([, videos]) => videos.length);
  }, [sources, query]);

  const currentId = display?.type === 'youtube' ? display.content?.video_id : null;
  const play = (videoUrl) =>
    run(videoUrl, () => api('POST', '/playback/youtube', { youtube_url: videoUrl, mute: !sound }));
  const playAny = (videoUrl) => (videoUrl.includes('twitch.tv')
    ? run(videoUrl, () => api('POST', '/playback/twitch', { twitch_url: videoUrl, mute: !sound }))
    : play(videoUrl));

  return (
    <div className="picker">
      <form className="url-row" onSubmit={(e) => { e.preventDefault(); if (url) playAny(url); }}>
        <input className="input mono" type="url" placeholder="YouTube or Twitch link"
               value={url} onChange={(e) => setUrl(e.target.value)} />
        <button className="btn primary" disabled={!url || busy}><Icon.play /> Play</button>
      </form>
      <div className="row-between">
        <label className="switch">
          <input type="checkbox" checked={sound} onChange={(e) => setSound(e.target.checked)} />
          <span className="switch-track" /> Play with sound
        </label>
        <label className="search">
          <Icon.search />
          <input placeholder="Search videos" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}

      {groups.map(([group, videos]) => (
        <section key={group} className="group">
          <h3 className="group-title">{groupName(group)}</h3>
          <div className="thumbs">
            {videos.map((v) => {
              const id = youtubeId(v.url);
              const on = id && id === currentId;
              return (
                <button key={v.url} className={`thumb ${on ? 'is-on' : ''}`}
                        disabled={busy === v.url} onClick={() => play(v.url)}>
                  <span className="thumb-img">
                    <VideoThumb id={id} />
                    {on && <span className="thumb-live">On air</span>}
                  </span>
                  <span className="thumb-name">{v.name.replace(/^[^\p{L}\p{N}]+/u, '')}</span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

// ── Screen: website, QR code, image ─────────────────────────────────────

const DURATIONS = [
  ['', 'Until stopped'], ['30', '30 seconds'], ['60', '1 minute'], ['300', '5 minutes'], ['1800', '30 minutes'],
];

export function ScreenPicker() {
  const [kind, setKind] = useState('website');
  const [value, setValue] = useState('');
  const [file, setFile] = useState(null);
  const [duration, setDuration] = useState('');
  const [done, setDone] = useState(false);
  const { busy, error, run } = useAction();

  const seconds = duration ? Number(duration) : undefined;
  const show = () => run('show', async () => {
    if (kind === 'website') {
      await api('POST', '/display/website', { url: value, duration: seconds });
    } else if (kind === 'qrcode') {
      await api('POST', '/display/qrcode', { content: value, duration: seconds });
    } else {
      const form = new FormData();
      form.append('file', file);
      // 0 means "until removed" for the upload route
      await api('POST', `/display/image?duration=${seconds || 0}`, form);
    }
    setDone(true);
    setTimeout(() => setDone(false), 1800);
  });

  const ready = kind === 'image' ? !!file : !!value.trim();

  return (
    <form className="picker screen-form" onSubmit={(e) => { e.preventDefault(); if (ready) show(); }}>
      <div className="segmented" role="tablist">
        {[['website', 'Website'], ['qrcode', 'QR code'], ['image', 'Image']].map(([k, label]) => (
          <button type="button" key={k} role="tab" aria-selected={kind === k}
                  className={kind === k ? 'is-on' : ''} onClick={() => { setKind(k); setValue(''); }}>
            {label}
          </button>
        ))}
      </div>

      {kind === 'image' ? (
        <label className="drop">
          <Icon.upload />
          <span>{file ? file.name : 'Choose an image'}</span>
          <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
      ) : (
        <input className="input mono" type={kind === 'website' ? 'url' : 'text'}
               placeholder={kind === 'website' ? 'https://example.com' : 'Text or link for the QR code'}
               value={value} onChange={(e) => setValue(e.target.value)} />
      )}

      <div className="row-between">
        <label className="select">
          <span>Show for</span>
          <select value={duration} onChange={(e) => setDuration(e.target.value)}>
            {DURATIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </label>
        <button className="btn primary" disabled={!ready || busy}>
          {done ? <><Icon.check /> Shown</> : <><Icon.screen /> Show</>}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
