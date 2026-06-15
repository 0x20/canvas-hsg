import { useState, useEffect, useRef, useMemo } from 'react';
import './Control.css';

const SOURCES = [
  { id: 'video', label: 'Video', hint: 'YouTube / direct URL', cap: 'video' },
  { id: 'audio', label: 'Audio', hint: 'Soma.FM / web radio',  cap: 'audio' },
  { id: 'cast',  label: 'Cast',  hint: 'Chromecast on network', cap: 'cast'  },
];

const TABS = ['Canvas', 'API', 'Status', 'Diagnostics'];

const FAV_KEY = 'hsg.canvas.favs';
const FLAVOR_KEY = 'hsg.canvas.flavor';

const Icon = {
  play:  (p) => <svg viewBox="0 0 24 24" {...p}><path d="M7 5v14l12-7z" fill="currentColor"/></svg>,
  pause: (p) => <svg viewBox="0 0 24 24" {...p}><path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor"/></svg>,
  stop:  (p) => <svg viewBox="0 0 24 24" {...p}><rect x="6" y="6" width="12" height="12" fill="currentColor"/></svg>,
  prev:  (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M18 5L7 12l11 7zM5 5v14"/></svg>,
  gear:  (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" {...p}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3h.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>,
  mute:  (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M11 5L6 9H3v6h3l5 4zM22 9l-6 6M16 9l6 6"/></svg>,
  vol:   (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M11 5L6 9H3v6h3l5 4zM16 8a5 5 0 0 1 0 8M19 5a9 9 0 0 1 0 14"/></svg>,
  link:  (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M10 14a4 4 0 0 0 5.6 0l3-3a4 4 0 0 0-5.6-5.6l-1 1M14 10a4 4 0 0 0-5.6 0l-3 3a4 4 0 0 0 5.6 5.6l1-1"/></svg>,
  cast:  (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6M2 12a8 8 0 0 1 8 8M2 16a4 4 0 0 1 4 4M2 20h.01"/></svg>,
  dot:   (p) => <svg viewBox="0 0 24 24" {...p}><circle cx="12" cy="12" r="4" fill="currentColor"/></svg>,
  refresh:(p)=> <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" {...p}><path d="M3 12a9 9 0 0 1 15.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.3L3 16M3 21v-5h5"/></svg>,
  sun:   (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" {...p}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>,
  moon:  (p) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" {...p}><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>,
};

const DARK_FLAVOR = 'cyber';
const LIGHT_FLAVOR = 'editorial';
const isDark = (f) => f !== LIGHT_FLAVOR;

const fmtTime = (s) => {
  if (!s || !isFinite(s)) return '0:00';
  const m = Math.floor(s / 60), r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, '0')}`;
};

async function api(method, path, data) {
  const init = { method, headers: { 'Content-Type': 'application/json' } };
  if (data != null) init.body = JSON.stringify(data);
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`);
  const t = r.headers.get('content-type') || '';
  return t.includes('application/json') ? r.json() : r.text();
}

const YT_RE = /(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/;
const extractYouTubeId = (url) => url && url.match(YT_RE)?.[1];

// YouTube oEmbed: CORS-enabled, no auth, ~150ms typical. Used for user-pasted
// URLs that aren't in our preset library.
async function fetchYouTubeTitle(url) {
  try {
    const r = await fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(url)}&format=json`);
    if (!r.ok) return null;
    const j = await r.json();
    return j.title || null;
  } catch { return null; }
}

// Clipboard write with execCommand fallback for non-secure-context origins
// (http://canvas.local from a laptop won't be a "secure context", so
// navigator.clipboard is undefined there).
async function copyToClipboard(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {}
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch { return false; }
}

// ── TopBar ──────────────────────────────────────────────────────────────
function TopBar({ tab, setTab, ip, flavor, onToggleFlavor }) {
  const dark = isDark(flavor);
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" />
        <span className="brand-name">HSG / canvas</span>
      </div>
      <nav className="nav">
        {TABS.map((t) => (
          <button key={t} className={t === tab ? 'is-active' : ''} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </nav>
      <div className="meta">
        {ip && <span className="ip">{ip}</span>}
        <button className="theme-toggle" onClick={onToggleFlavor}
                title={dark ? 'switch to day' : 'switch to night'}
                aria-label={dark ? 'switch to day' : 'switch to night'}>
          {dark ? <Icon.sun width="15" height="15" /> : <Icon.moon width="15" height="15" />}
        </button>
      </div>
    </header>
  );
}

// ── SourceSwitch ────────────────────────────────────────────────────────
function SourceSwitch({ value, onChange, rightSlot }) {
  return (
    <div className="src-wrap">
      <div className="src-switch" role="tablist">
        {SOURCES.map((s, i) => (
          <button key={s.id} role="tab" aria-selected={s.id === value}
                  className={s.id === value ? 'src-tab is-on' : 'src-tab'}
                  onClick={() => onChange(s.id)}>
            <span className="src-tab-num">{String(i + 1).padStart(2, '0')}</span>
            <span className="src-tab-label">{s.label}</span>
            <span className="src-tab-hint">{s.hint}</span>
          </button>
        ))}
      </div>
      {rightSlot && (
        <div className="src-output-rail">
          <span className="src-output-arrow" aria-hidden="true">→</span>
          <span className="src-output-lbl">routes to</span>
          {rightSlot}
        </div>
      )}
    </div>
  );
}

// ── OutputGear ──────────────────────────────────────────────────────────
function OutputGear({ value, options, onChange, onRescan }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const off = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    window.addEventListener('mousedown', off);
    return () => window.removeEventListener('mousedown', off);
  }, [open]);
  const display = options.find((o) => o.id === value)?.name || 'select';
  return (
    <div className="gear-wrap" ref={ref}>
      <button className={open ? 'gear is-on' : 'gear'} onClick={() => setOpen((o) => !o)} title="Output routing">
        <Icon.gear width="14" height="14" />
        <span className="gear-val">{display}</span>
      </button>
      {open && (
        <div className="gear-pop">
          <div className="gear-pop-hd">Output target</div>
          {options.map((o) => (
            <button key={o.id} className={o.id === value ? 'gear-opt is-on' : 'gear-opt'}
                    onClick={() => { onChange(o.id); setOpen(false); }}>
              {o.name}
              {o.id === value && <span className="gear-opt-dot" />}
            </button>
          ))}
          {onRescan && (
            <button className="gear-opt gear-refresh" onClick={() => { onRescan(); setOpen(false); }}>
              <Icon.refresh width="12" height="12" />Re-scan
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function StarIcon({ filled }) {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13"
         fill={filled ? 'currentColor' : 'none'}
         stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round">
      <path d="m12 3 2.7 5.7 6.3.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.3-.9L12 3z"/>
    </svg>
  );
}

// ── VideoPanel ──────────────────────────────────────────────────────────
function VideoPanel({ presets, state, set, favs, toggleFav, onPlay }) {
  const [query, setQuery] = useState('');
  const [cat, setCat] = useState('all');
  const [open, setOpen] = useState(false);

  const categories = useMemo(() => ['all', ...new Set(presets.map((p) => p.cat))], [presets]);
  const counts = useMemo(() => {
    const m = { all: presets.length };
    for (const p of presets) m[p.cat] = (m[p.cat] || 0) + 1;
    return m;
  }, [presets]);

  const favList = presets.filter((p) => favs.has(p.id));
  const q = query.trim().toLowerCase();
  const filtered = presets.filter((p) => {
    if (cat !== 'all' && p.cat !== cat) return false;
    if (q && !p.label.toLowerCase().includes(q) && !p.cat.toLowerCase().includes(q)) return false;
    return true;
  });

  return (
    <div className="panel">
      <div className="panel-row">
        <label className="field">
          <span className="field-lbl">URL</span>
          <input className="field-in mono" value={state.url}
                 placeholder="paste a youtube or direct video url"
                 onChange={(e) => set({ url: e.target.value, presetId: null, title: '' })} />
          <span className="field-affix"><Icon.link width="14" height="14" /></span>
        </label>
      </div>

      <div className="panel-row">
        <div className="field-lbl as-head with-action">
          Quick select
          <span className="micro-note mono">
            {favList.length} favorite{favList.length === 1 ? '' : 's'} · {presets.length} total
          </span>
        </div>

        <div className="fav-row">
          {favList.map((p) => (
            <button key={p.id}
                    className={state.presetId === p.id ? 'fav-chip is-on' : 'fav-chip'}
                    onClick={() => onPlay(p)}>
              <span className="fav-chip-star"><StarIcon filled /></span>
              <span className="fav-chip-label">{p.label.split(' · ')[0]}</span>
            </button>
          ))}
          <button className={open ? 'fav-chip more is-on' : 'fav-chip more'}
                  onClick={() => setOpen((o) => !o)}>
            <span className="fav-chip-label">
              {open ? 'close library' : `browse all (${presets.length})`}
            </span>
            <span className="fav-chip-caret" aria-hidden="true">{open ? '−' : '+'}</span>
          </button>
        </div>

        {open && (
          <div className="library">
            <div className="library-tools">
              <label className="search">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <circle cx="11" cy="11" r="6"/><path d="m20 20-4-4"/>
                </svg>
                <input value={query} onChange={(e) => setQuery(e.target.value)}
                       placeholder="search title or category…" className="search-in mono" />
                {query && <button className="search-clear" onClick={() => setQuery('')}>✕</button>}
              </label>
              <div className="cat-row">
                {categories.map((c) => (
                  <button key={c} className={c === cat ? 'cat is-on' : 'cat'}
                          onClick={() => setCat(c)}>
                    {c}<span className="cat-n mono">{counts[c] || 0}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="lib-list">
              {filtered.length === 0 && (
                <div className="lib-empty mono">no presets match “{query}”</div>
              )}
              {filtered.map((p) => {
                const isFav = favs.has(p.id);
                const isOn = state.presetId === p.id;
                return (
                  <div key={p.id} className={isOn ? 'lib-row is-on' : 'lib-row'}>
                    <button className="lib-row-main"
                            onClick={() => onPlay(p)}>
                      <span className="lib-cat mono">{p.cat}</span>
                      <span className="lib-title">{p.label}</span>
                    </button>
                    <button className={isFav ? 'lib-star is-on' : 'lib-star'}
                            onClick={(e) => { e.stopPropagation(); toggleFav(p.id); }}
                            aria-label={isFav ? 'Unfavorite' : 'Favorite'}>
                      <StarIcon filled={isFav} />
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="panel-row inline-opts">
        <label className="opt">
          <input type="checkbox" checked={!state.audio}
                 onChange={(e) => set({ audio: !e.target.checked })} />
          <span>Mute audio</span>
        </label>
        <label className="opt">
          <span className="opt-lbl">Duration</span>
          <input className="field-in mono compact" placeholder="∞" type="number" min="0"
                 value={state.duration} onChange={(e) => set({ duration: e.target.value })} />
          <span className="opt-suffix">sec</span>
        </label>
      </div>
    </div>
  );
}

// ── AudioPanel ──────────────────────────────────────────────────────────
function AudioPanel({ streams, state, set, onPlay }) {
  return (
    <div className="panel">
      <div className="panel-row">
        <div className="field-lbl as-head">Streams</div>
        <div className="stream-list">
          {streams.map((s) => (
            <button key={s.id}
                    className={state.streamId === s.id ? 'stream is-on' : 'stream'}
                    onClick={() => onPlay(s)}>
              <span className="stream-eq" aria-hidden="true"><i /><i /><i /><i /></span>
              <span className="stream-label">{s.label}</span>
              <span className="stream-tag">{s.tag}</span>
              <span />{/* spacer to keep grid alignment */}
            </button>
          ))}
          {streams.length === 0 && <div className="lib-empty mono">no streams configured</div>}
        </div>
      </div>
      <div className="panel-row">
        <label className="field">
          <span className="field-lbl">Or paste URL</span>
          <input className="field-in mono" placeholder="https://stream.example/audio.mp3"
                 value={state.url} onChange={(e) => set({ url: e.target.value, streamId: null, title: '' })} />
        </label>
      </div>
    </div>
  );
}

// ── CastPanel ───────────────────────────────────────────────────────────
function CastPanel({ devices, state, set, onRescan }) {
  return (
    <div className="panel">
      <div className="panel-row">
        <div className="field-lbl as-head with-action">
          Devices on network
          <button className="micro-btn" onClick={onRescan}>
            <Icon.refresh width="12" height="12" />Re-discover
          </button>
        </div>
        <div className="device-list">
          {devices.length === 0 && <div className="lib-empty mono">no cast devices found</div>}
          {devices.map((d) => (
            <button key={d.id}
                    className={state.deviceId === d.id ? 'device is-on' : 'device'}
                    onClick={() => set({ deviceId: d.id, title: d.name })}>
              <span className="device-mark"><Icon.cast width="14" height="14" /></span>
              <span className="device-label">{d.name}</span>
              <span className="device-meta">{d.kind || 'Cast'}</span>
              <span className="device-state s-idle">ready</span>
            </button>
          ))}
        </div>
      </div>
      <div className="panel-row">
        <label className="field">
          <span className="field-lbl">Media URL</span>
          <input className="field-in mono" placeholder="https://…/track.mp3 or http://…/stream"
                 value={state.url} onChange={(e) => set({ url: e.target.value })} />
        </label>
      </div>
    </div>
  );
}

// ── NowPlayingFooter ────────────────────────────────────────────────────
function NowPlayingFooter({ playing, source, title, position, duration, volume, muted,
                            onPlayPause, onStop, onSeek, onVol, onMute, canPlay }) {
  const trackRef = useRef(null);
  const onScrub = (e) => {
    if (!duration) return;
    const r = trackRef.current.getBoundingClientRect();
    const pct = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    onSeek?.(pct * duration);
  };
  return (
    <footer className="now">
      <div className="now-meta">
        <span className={`now-led ${playing ? 'is-on' : ''}`} />
        <div className="now-text">
          <span className="now-source">{source || '—'}</span>
          <span className="now-title">{title || '— idle —'}</span>
        </div>
      </div>
      <div className="now-transport">
        <button className="t-btn ghost" onClick={() => onSeek?.(0)} title="Restart" disabled={!duration}>
          <Icon.prev width="18" height="18" />
        </button>
        <button className="t-btn primary" onClick={onPlayPause} disabled={!canPlay && !playing}
                aria-label={playing ? 'Pause' : 'Play'}>
          {playing ? <Icon.pause width="18" height="18" /> : <Icon.play width="18" height="18" />}
        </button>
        <button className="t-btn ghost" onClick={onStop} title="Stop" disabled={!playing}>
          <Icon.stop width="14" height="14" />
        </button>
      </div>
      <div className="now-scrub">
        <span className="time mono">{fmtTime(position)}</span>
        <div ref={trackRef} className="scrub" onClick={onScrub}>
          <div className="scrub-fill"
               style={{ width: `${duration ? (position / duration) * 100 : 0}%` }} />
          {!!duration && (
            <div className="scrub-thumb"
                 style={{ left: `${(position / duration) * 100}%` }} />
          )}
        </div>
        <span className="time mono">{duration ? fmtTime(duration) : '—'}</span>
      </div>
      <div className="now-vol">
        <button className="vol-mute" onClick={onMute} aria-label={muted ? 'Unmute' : 'Mute'}>
          {muted ? <Icon.mute width="16" height="16" /> : <Icon.vol width="16" height="16" />}
        </button>
        <input type="range" className="vol-slider" min="0" max="100"
               value={muted ? 0 : volume}
               onChange={(e) => onVol(Number(e.target.value))} />
        <span className="vol-val mono">{muted ? '—' : `${volume}`}</span>
      </div>
    </footer>
  );
}

// ── StatusView ──────────────────────────────────────────────────────────
function StatusBlock({ title, rows }) {
  return (
    <div className="status-block">
      <div className="section-head">
        <span className="section-eyebrow">{title}</span>
      </div>
      <div className="state-card">
        {rows.map(([k, v], i) => (
          <div className="state-row" key={i}>
            <span className="state-k">{k}</span>
            <span className="state-v mono truncate">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatusView() {
  const [data, setData] = useState({});
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const fetch1 = (p) => api('GET', p).catch(() => null);
      const [health, status, diag, targets, cec, spotify, stack] = await Promise.all([
        fetch1('/health'), fetch1('/status'), fetch1('/diagnostics'),
        fetch1('/targets/status'), fetch1('/cec/status'),
        fetch1('/audio/spotify/status'), fetch1('/display/stack'),
      ]);
      if (cancelled) return;
      setData({ health, status, diag, targets, cec, spotify, stack });
    };
    load();
    return () => { cancelled = true; };
  }, [tick]);

  const t = data.targets;
  const targetSummary = t
    ? `${t.available_targets}/${t.total_targets} available · video → ${t.active_video_target || '—'} · audio → ${t.active_audio_target || '—'}`
    : '—';
  return (
    <main className="main tab-view">
      <div className="tab-head">
        <div className="section-head">
          <span className="section-eyebrow">02 · Status</span>
          <h1 className="section-title">System health</h1>
        </div>
        <button className="micro-btn" onClick={() => setTick((n) => n + 1)}>
          <Icon.refresh width="12" height="12" />Refresh
        </button>
      </div>
      <div className="status-grid">
        <StatusBlock title="Service" rows={[
          ['Status', data.health?.status || '—'],
          ['Version', data.health?.version || '—'],
          ['Arch', data.health?.architecture || '—'],
          ['Engine', data.status?.engine || '—'],
          ['Display', data.status?.display || '—'],
          ['Audio', data.status?.audio || '—'],
        ]} />
        <StatusBlock title="Hardware" rows={[
          ['User', data.diag?.user || '—'],
          ['Display env', data.diag?.display_env || '—'],
          ['Audio device', data.diag?.audio_device || '—'],
          ['Connector', data.diag?.display?.optimal_connector || '—'],
          ['Capabilities', data.diag?.display?.capabilities_detected ?? '—'],
        ]} />
        <StatusBlock title="Targets" rows={[
          ['Summary', targetSummary],
          ...(t?.targets || []).slice(0, 6).map((tg) => [
            tg.name,
            `${tg.capabilities?.join(', ') || ''} · ${tg.is_available ? 'ready' : 'offline'}`,
          ]),
        ]} />
        <StatusBlock title="CEC / TV" rows={[
          ['Adapter', data.cec?.adapter || '—'],
          ['Available', data.cec?.available ? 'yes' : 'no'],
          ['Power', data.cec?.tv_power?.power_status || '—'],
          ['Devices', data.cec?.devices_found ?? 0],
        ]} />
        <StatusBlock title="Spotify" rows={[
          ['Service', data.spotify?.service_active ? 'active' : 'inactive'],
          ['Playing', data.spotify?.is_playing ? 'yes' : 'no'],
          ['Track', data.spotify?.track?.name || '—'],
          ['Artist', data.spotify?.track?.artists || '—'],
        ]} />
        <StatusBlock title="Display stack" rows={[
          ['Current', data.stack?.current?.type || '—'],
          ['Id', data.stack?.current?.id || '—'],
          ['Depth', data.stack?.stack?.length ?? 0],
        ]} />
      </div>
    </main>
  );
}

// ── DiagnosticsView ─────────────────────────────────────────────────────
function ActionBtn({ label, onClick, danger }) {
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(null); // true | false | null
  const run = async () => {
    setBusy(true);
    setOk(null);
    try { await onClick(); setOk(true); }
    catch { setOk(false); }
    setBusy(false);
    setTimeout(() => setOk(null), 1500);
  };
  const cls = `diag-btn${danger ? ' danger' : ''}${ok === true ? ' ok' : ''}${ok === false ? ' err' : ''}`;
  return (
    <button className={cls} disabled={busy} onClick={run}>
      {busy ? '…' : ok === true ? '✓' : ok === false ? '✕' : null}
      <span>{label}</span>
    </button>
  );
}

function DiagnosticsView() {
  const [diag, setDiag] = useState(null);
  const [tick, setTick] = useState(0);
  const [overlays, setOverlays] = useState(null);
  useEffect(() => {
    api('GET', '/diagnostics').then(setDiag).catch(() => setDiag(null));
    api('GET', '/background/overlays').then(setOverlays).catch(() => setOverlays(null));
  }, [tick]);

  const setOverlay = (patch) => {
    setOverlays((cur) => ({ ...(cur || {}), ...patch })); // optimistic update
    api('POST', '/background/overlays', patch).then(setOverlays).catch(() => {});
  };
  return (
    <main className="main tab-view">
      <div className="tab-head">
        <div className="section-head">
          <span className="section-eyebrow">03 · Diagnostics</span>
          <h1 className="section-title">Probes & actions</h1>
        </div>
        <button className="micro-btn" onClick={() => setTick((n) => n + 1)}>
          <Icon.refresh width="12" height="12" />Refresh
        </button>
      </div>
      <div className="section-head">
        <span className="section-eyebrow">Actions</span>
      </div>
      <div className="diag-grid">
        <ActionBtn label="Reload kiosk page" onClick={() => api('POST', '/display/reload')} />
        <ActionBtn label="Stop all playback" onClick={async () => {
          await api('DELETE', '/playback/stop'); await api('POST', '/audio/stop').catch(() => {});
        }} />
        <ActionBtn label="Re-scan output targets" onClick={() => api('POST', '/targets/refresh')} />
        <ActionBtn label="Re-discover Chromecast" onClick={() => api('GET', '/chromecast/discover')} />
        <ActionBtn label="TV power on" onClick={() => api('POST', '/cec/tv/power-on')} />
        <ActionBtn label="TV power off" onClick={() => api('POST', '/cec/tv/power-off')} danger />
        <ActionBtn label="Show background" onClick={() => api('POST', '/background/show')} />
      </div>
      <div className="section-head" style={{ marginTop: 24 }}>
        <span className="section-eyebrow">Idle screen overlays</span>
      </div>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <label className="opt">
          <input type="checkbox" checked={overlays?.show_logo ?? true}
                 onChange={(e) => setOverlay({ show_logo: e.target.checked })} />
          Show logo
        </label>
        <label className="opt">
          <input type="checkbox" checked={overlays?.show_qr ?? true}
                 onChange={(e) => setOverlay({ show_qr: e.target.checked })} />
          Show QR code
        </label>
      </div>
      <div className="section-head" style={{ marginTop: 24 }}>
        <span className="section-eyebrow">Raw /diagnostics</span>
      </div>
      <pre className="raw-json">{diag ? JSON.stringify(diag, null, 2) : '—'}</pre>
    </main>
  );
}

// ── ApiView ─────────────────────────────────────────────────────────────
function ApiView() {
  return (
    <main className="main tab-view">
      <div className="tab-head">
        <div className="section-head">
          <span className="section-eyebrow">01 · API</span>
          <h1 className="section-title">Interactive docs</h1>
        </div>
      </div>
      <div className="api-links">
        <a className="api-link" href="/docs" target="_blank" rel="noreferrer">
          <span className="api-link-eyebrow mono">Swagger UI</span>
          <span className="api-link-title">/docs</span>
          <span className="api-link-hint">Try every endpoint live with request bodies and response schemas.</span>
        </a>
        <a className="api-link" href="/redoc" target="_blank" rel="noreferrer">
          <span className="api-link-eyebrow mono">ReDoc</span>
          <span className="api-link-title">/redoc</span>
          <span className="api-link-hint">Cleaner, read-only API reference, easier on the eyes for browsing.</span>
        </a>
        <a className="api-link" href="/openapi.json" target="_blank" rel="noreferrer">
          <span className="api-link-eyebrow mono">OpenAPI schema</span>
          <span className="api-link-title">/openapi.json</span>
          <span className="api-link-hint">Raw spec — pipe through `jq` or import into Postman / Bruno.</span>
        </a>
      </div>
    </main>
  );
}

// ── Root ────────────────────────────────────────────────────────────────
export default function Control() {
  const [tab, setTab] = useState('Canvas');
  const [source, setSource] = useState('video');
  const [online, setOnline] = useState(true);
  const [flavor, setFlavor] = useState(() => localStorage.getItem(FLAVOR_KEY) || 'cyber');

  const [videoPresets, setVideoPresets] = useState([]);
  const [audioStreams, setAudioStreams] = useState([]);
  const [castDevices, setCastDevices] = useState([]);
  const [targets, setTargets] = useState([]);
  const [outBySource, setOutBySource] = useState({});

  const [videoState, setVideoState] = useState({ url: '', presetId: null, title: '', audio: true, duration: '' });
  const [audioState, setAudioState] = useState({ url: '', streamId: null, title: '' });
  const [castState,  setCastState]  = useState({ url: '', deviceId: null, title: '' });

  const [displayItem, setDisplayItem] = useState(null);
  const [activeTitle, setActiveTitle] = useState('');
  const [volume, setVolume] = useState(70);
  const [muted, setMuted] = useState(false);
  const [history, setHistory] = useState([]);
  const [copiedId, setCopiedId] = useState(null);

  // Refs let the /ws/display callback (mounted once) read the latest catalogs
  // without resubscribing whenever presets load.
  const videoPresetsRef = useRef([]);
  const audioStreamsRef = useRef([]);
  const titleCacheRef = useRef(new Map());
  useEffect(() => { videoPresetsRef.current = videoPresets; }, [videoPresets]);
  useEffect(() => { audioStreamsRef.current = audioStreams; }, [audioStreams]);

  const [favs, setFavs] = useState(() => {
    try { return new Set(JSON.parse(localStorage.getItem(FAV_KEY) || '[]')); }
    catch { return new Set(); }
  });
  const toggleFav = (id) => setFavs((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    localStorage.setItem(FAV_KEY, JSON.stringify([...n]));
    return n;
  });

  useEffect(() => {
    localStorage.setItem(FLAVOR_KEY, flavor);
  }, [flavor]);

  // ── Load static catalogs (presets, targets) ──────────────────────────
  const loadTargets = async () => {
    try {
      const data = await api('GET', '/targets');
      const all = data.targets || [];
      setTargets(all);
      const cast = all.filter((t) => t.type?.startsWith('chromecast') || t.type === 'chromecast');
      setCastDevices(cast.map((d) => ({ id: d.id, name: d.name, kind: 'Chromecast' })));

      // pick default output per source if not already set
      setOutBySource((prev) => {
        const next = { ...prev };
        const defaultFor = (cap) => {
          const t = all.find((x) => x.capabilities?.includes(cap) && x.metadata?.is_default && x.is_available);
          return t?.id || all.find((x) => x.capabilities?.includes(cap) && x.is_available)?.id;
        };
        if (!next.video) next.video = defaultFor('video');
        if (!next.audio) next.audio = defaultFor('audio');
        if (!next.cast)  next.cast  = cast[0]?.id;
        return next;
      });
    } catch (e) { console.error('Failed to load targets:', e); }
  };

  useEffect(() => {
    (async () => {
      try {
        const sources = await api('GET', '/media-sources');
        // Flatten youtube_channels into a single preset list with category
        const flat = [];
        for (const [cat, vids] of Object.entries(sources.youtube_channels || {})) {
          // Shorten category labels for the UI
          const shortCat = cat.replace(/_/g, ' ');
          for (const v of vids) {
            flat.push({
              id: `${cat}-${v.url.split('=').pop().slice(0, 6)}`,
              label: v.name.replace(/^[^\w\s]+/, '').trim(),
              cat: shortCat,
              url: v.url,
            });
          }
        }
        setVideoPresets(flat);

        const streams = [];
        for (const [tag, list] of Object.entries(sources.music_streams || {})) {
          for (const s of list) {
            streams.push({
              id: `${tag}-${s.name.replace(/\s+/g, '-').toLowerCase()}`,
              label: s.name,
              tag: tag.toUpperCase(),
              url: s.url,
            });
          }
        }
        setAudioStreams(streams);
      } catch (e) { console.error('Failed to load media sources:', e); }
    })();
    loadTargets();

    // Current volume
    api('GET', '/playback/volume').then((d) => {
      if (typeof d?.volume === 'number') setVolume(d.volume);
    }).catch(() => {});
  }, []);

  // ── Title resolution ─────────────────────────────────────────────────
  // Synchronous lookup against preset/stream catalogs first; falls back to
  // oEmbed (cached) for YouTube URLs the user pasted by hand. Used by both
  // the history list and the now-playing footer so they stay in sync.
  const resolveTitleSync = (item) => {
    if (!item) return '';
    const url = item.content?.url || '';
    const ytId = extractYouTubeId(url);
    return (
      item.content?.title ||
      item.content?.name ||
      (ytId && videoPresetsRef.current.find((p) => extractYouTubeId(p.url) === ytId)?.label) ||
      (url && audioStreamsRef.current.find((s) => s.url === url)?.label) ||
      titleCacheRef.current.get(url) ||
      ''
    );
  };

  // Resolve and notify via onResolved(title) whenever a better title becomes
  // available (sync hit → onResolved fires once; oEmbed miss → may fire a
  // second time once the fetch completes).
  const resolveTitle = (item, onResolved) => {
    const sync = resolveTitleSync(item);
    if (sync) { onResolved(sync); return; }
    const url = item?.content?.url || '';
    const ytId = extractYouTubeId(url);
    if (ytId && !titleCacheRef.current.has(url)) {
      fetchYouTubeTitle(url).then((title) => {
        if (!title) return;
        titleCacheRef.current.set(url, title);
        onResolved(title);
      });
    }
  };

  const pushHistory = (item) => {
    const url = item.content?.url || '';
    const stamp = new Date();
    const hh = String(stamp.getHours()).padStart(2, '0');
    const mm = String(stamp.getMinutes()).padStart(2, '0');
    const id = `${stamp.getTime()}-${item.id || extractYouTubeId(url) || Math.random().toString(36).slice(2, 7)}`;
    const initial = resolveTitleSync(item) || '(loading title…)';
    setHistory((h) => [{ id, time: `${hh}:${mm}`, source: item.type, title: initial, url }, ...h].slice(0, 8));
    if (initial === '(loading title…)') {
      resolveTitle(item, (t) =>
        setHistory((h) => h.map((e) => (e.id === id ? { ...e, title: t } : e)))
      );
    }
  };

  const copyHistoryUrl = async (entry) => {
    if (!entry.url) return;
    const ok = await copyToClipboard(entry.url);
    if (ok) {
      setCopiedId(entry.id);
      setTimeout(() => setCopiedId((c) => (c === entry.id ? null : c)), 1400);
    }
  };

  // ── Resolve activeTitle whenever displayItem changes ─────────────────
  useEffect(() => {
    if (!displayItem || displayItem.type === 'static') {
      setActiveTitle('');
      return;
    }
    setActiveTitle(resolveTitleSync(displayItem));
    resolveTitle(displayItem, setActiveTitle);
    // resolveTitle/resolveTitleSync close over refs only, so we don't need
    // them in deps — they're stable across renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayItem]);

  // ── /ws/display: track active display item ───────────────────────────
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const port = window.location.port ? `:${window.location.port}` : '';
    const wsUrl = `${protocol}//${window.location.hostname}${port}/ws/display`;
    let ws = null, retry = null;
    const connect = () => {
      try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => setOnline(true);
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (msg.event === 'display_state') {
              setDisplayItem(msg.data);
              if (msg.data && msg.data.type !== 'static') {
                pushHistory(msg.data);
              }
            }
          } catch {}
        };
        ws.onerror = () => {};
        ws.onclose = () => { setOnline(false); retry = setTimeout(connect, 2000); };
      } catch { retry = setTimeout(connect, 2000); }
    };
    connect();
    return () => { if (retry) clearTimeout(retry); if (ws) ws.close(); };
  }, []);

  // ── Source-aware current state ───────────────────────────────────────
  const cur = source === 'video' ? videoState : source === 'audio' ? audioState : castState;
  const setCur = (patch) => {
    if (source === 'video') setVideoState((s) => ({ ...s, ...patch }));
    else if (source === 'audio') setAudioState((s) => ({ ...s, ...patch }));
    else setCastState((s) => ({ ...s, ...patch }));
  };

  // ── Target options for the current source's gear ─────────────────────
  const gearOptions = useMemo(() => {
    if (source === 'cast') {
      return castDevices.map((d) => ({ id: d.id, name: d.name }));
    }
    const cap = source === 'video' ? 'video' : 'audio';
    return targets
      .filter((t) => t.capabilities?.includes(cap) && t.is_available)
      .map((t) => ({ id: t.id, name: t.name }));
  }, [source, targets, castDevices]);

  // ── Active display state derived from displayItem ────────────────────
  const activeType = displayItem?.type;
  const isPlaying = activeType && activeType !== 'static';
  const activeSourceLabel = (() => {
    switch (activeType) {
      case 'youtube': return 'Video';
      case 'audio':   return 'Audio';
      case 'website': return 'Website';
      case 'image':
      case 'qrcode':  return 'Image';
      case 'spotify': return 'Spotify';
      case 'sendspin':return 'Sendspin';
      case 'bluetooth':return 'Bluetooth';
      case 'video':   return 'Video';
      default:        return 'Idle';
    }
  })();

  // ── Handlers ─────────────────────────────────────────────────────────
  // Used by preset/stream clicks in the source panels: update local state
  // (so the chip / row shows selected) AND issue the play call with the
  // explicit URL — state setters are async, the request can't read them yet.
  const playPreset = async (preset) => {
    if (source === 'video') {
      setVideoState((s) => ({ ...s, url: preset.url, presetId: preset.id, title: preset.label }));
      try {
        const target = outBySource.video;
        const body = { youtube_url: preset.url, mute: !videoState.audio };
        if (videoState.duration) body.duration = parseInt(videoState.duration, 10);
        const path = `/targets/play/video${target ? `?target=${encodeURIComponent(target)}` : ''}`;
        await api('POST', path, body);
      } catch (e) { console.error('playPreset video failed:', e); }
    } else if (source === 'audio') {
      setAudioState((s) => ({ ...s, url: preset.url, streamId: preset.id, title: preset.label }));
      try {
        const target = outBySource.audio;
        const path = `/targets/play/audio${target ? `?target=${encodeURIComponent(target)}` : ''}`;
        await api('POST', path, { stream_url: preset.url });
      } catch (e) { console.error('playPreset audio failed:', e); }
    }
  };

  const playCurrent = async () => {
    try {
      if (source === 'video') {
        if (!videoState.url) return;
        const target = outBySource.video;
        const body = { youtube_url: videoState.url, mute: !videoState.audio };
        if (videoState.duration) body.duration = parseInt(videoState.duration, 10);
        const path = `/targets/play/video${target ? `?target=${encodeURIComponent(target)}` : ''}`;
        await api('POST', path, body);
      } else if (source === 'audio') {
        if (!audioState.url) return;
        const target = outBySource.audio;
        const path = `/targets/play/audio${target ? `?target=${encodeURIComponent(target)}` : ''}`;
        await api('POST', path, { stream_url: audioState.url });
      } else if (source === 'cast') {
        if (!castState.url || !castState.deviceId) return;
        await api('POST', '/chromecast/start', {
          url: castState.url,
          target_id: castState.deviceId,
        });
      }
    } catch (e) { console.error('play failed:', e); }
  };

  const stopAll = async () => {
    try {
      await api('DELETE', '/playback/stop');
    } catch {}
    try {
      await api('POST', '/audio/stop');
    } catch {}
  };

  const setVol = async (v) => {
    setVolume(v);
    try { await api('PUT', '/playback/volume', { volume: v }); } catch {}
  };

  const rescanCast = async () => {
    try { await api('POST', '/targets/refresh'); } catch {}
    await loadTargets();
  };

  const canPlay = (source === 'video' && !!videoState.url) ||
                  (source === 'audio' && !!audioState.url) ||
                  (source === 'cast'  && !!castState.url && !!castState.deviceId);

  return (
    <div className={`control-root flavor-${flavor}`}>
      <div className="app">
        <div className="bg-grid" aria-hidden="true" />
        <div className="bg-vignette" aria-hidden="true" />

        <TopBar tab={tab} setTab={setTab} ip={window.location.hostname}
                flavor={flavor}
                onToggleFlavor={() => setFlavor((f) => isDark(f) ? LIGHT_FLAVOR : DARK_FLAVOR)} />

        {tab === 'API' && <ApiView />}
        {tab === 'Status' && <StatusView />}
        {tab === 'Diagnostics' && <DiagnosticsView />}
        {tab === 'Canvas' && (
        <main className="main">
          <div className="col-left">
            <div className="section-head">
              <span className="section-eyebrow">01 · Source</span>
              <h1 className="section-title">What's casting</h1>
            </div>
            <SourceSwitch value={source} onChange={setSource}
                          rightSlot={
                            gearOptions.length > 0 && (
                              <OutputGear
                                value={outBySource[source]}
                                options={gearOptions}
                                onChange={(v) => setOutBySource((m) => ({ ...m, [source]: v }))}
                                onRescan={source === 'cast' ? rescanCast : null}
                              />
                            )
                          } />

            {source === 'video' && (
              <VideoPanel presets={videoPresets} state={videoState} set={setCur}
                          favs={favs} toggleFav={toggleFav} onPlay={playPreset} />
            )}
            {source === 'audio' && (
              <AudioPanel streams={audioStreams} state={audioState} set={setCur}
                          onPlay={playPreset} />
            )}
            {source === 'cast' && (
              <CastPanel devices={castDevices} state={castState} set={setCur}
                         onRescan={rescanCast} />
            )}
          </div>

          <aside className="col-right">
            <div className="section-head">
              <span className="section-eyebrow">02 · State</span>
              <h2 className="section-title">Live</h2>
            </div>
            <div className="state-card">
              <div className="state-row">
                <span className="state-k">Source</span>
                <span className="state-v">{activeSourceLabel}</span>
              </div>
              <div className="state-row">
                <span className="state-k">Output</span>
                <span className="state-v mono">
                  {gearOptions.find((o) => o.id === outBySource[source])?.name || '—'}
                </span>
              </div>
              <div className="state-row">
                <span className="state-k">Status</span>
                <span className={`state-v badge ${isPlaying ? 'b-on' : 'b-idle'}`}>
                  <Icon.dot width="8" height="8" />
                  {isPlaying ? 'playing' : 'idle'}
                </span>
              </div>
              <div className="state-row">
                <span className="state-k">Now</span>
                <span className="state-v truncate">{activeTitle || '—'}</span>
              </div>
            </div>

            <div className="section-head">
              <span className="section-eyebrow">03 · Recent</span>
              <h2 className="section-title">History</h2>
            </div>
            <ul className="history">
              {history.length === 0 && (
                <li className="h-empty">
                  <span className="h-time mono">—</span><span className="h-source">—</span>
                  <span className="h-title">nothing yet</span>
                </li>
              )}
              {history.map((h) => {
                const copied = copiedId === h.id;
                const clickable = !!h.url;
                return (
                  <li key={h.id}
                      className={`${clickable ? 'h-clickable' : ''} ${copied ? 'h-copied' : ''}`.trim()}
                      onClick={clickable ? () => copyHistoryUrl(h) : undefined}
                      title={clickable ? (copied ? 'copied!' : `click to copy ${h.url}`) : undefined}>
                    <span className="h-time mono">{h.time}</span>
                    <span className="h-source">{h.source}</span>
                    <span className="h-title">{copied ? 'copied!' : h.title}</span>
                  </li>
                );
              })}
            </ul>
          </aside>
        </main>
        )}

        <NowPlayingFooter
          playing={isPlaying}
          source={activeSourceLabel}
          title={activeTitle}
          position={0}
          duration={0}
          volume={volume}
          muted={muted}
          canPlay={canPlay}
          onPlayPause={isPlaying ? stopAll : playCurrent}
          onStop={stopAll}
          onVol={setVol}
          onMute={() => setMuted((m) => !m)}
        />
      </div>
    </div>
  );
}
