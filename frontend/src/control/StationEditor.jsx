import { useEffect, useMemo, useState } from 'react';
import { api, hostOf, somafmLogo } from './api';
import { Icon } from './icons';

let nextKey = 1;
// savedUrl: the URL as saved on the server, so "Detect again" is offered only
// for a station the server knows
const withKeys = (groups) => groups.map((g) => ({
  ...g, key: nextKey++, stations: g.stations.map((s) => ({ ...s, key: nextKey++, savedUrl: s.url })),
}));
/** A copy of obj without the given fields. */
const omit = (obj, ...fields) => Object.fromEntries(Object.entries(obj).filter(([k]) => !fields.includes(k)));

// The editor-only fields: React keys and the "user typed here" flag
const withoutKeys = (groups) => groups.map((g) => ({
  ...omit(g, 'key', 'stations'),
  stations: g.stations.map((s) => omit(s, 'key', 'touched', 'savedUrl')),
}));

const URL_RE = /^https?:\/\/\S+$/;
const imageOk = (s) => !(s.image || '').trim() || URL_RE.test(s.image.trim());
const stationOk = (s) => s.name.trim() && URL_RE.test(s.url.trim()) && imageOk(s);

/** Move item i of list by delta (-1 up, +1 down); returns a new list. */
function move(list, i, delta) {
  const j = i + delta;
  if (j < 0 || j >= list.length) return list;
  const copy = [...list];
  [copy[i], copy[j]] = [copy[j], copy[i]];
  return copy;
}

function IconButton({ label, onClick, disabled, children, danger }) {
  return (
    <button type="button" className={`icon-btn ${danger ? 'danger' : ''}`} aria-label={label} title={label}
            disabled={disabled} onClick={onClick}>
      {children}
    </button>
  );
}

function Thumb({ src, name }) {
  const [failed, setFailed] = useState(false);
  return (
    <span className="edit-thumb" aria-hidden="true">
      {src && !failed
        ? <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
        : <span className="monogram">{(name || '?').slice(0, 2)}</span>}
    </span>
  );
}

const PROVIDERS = { somafm: 'SomaFM', radioparadise: 'Radio Paradise', fip: 'Radio France', kexp: 'KEXP', bbc: 'BBC', willy: 'Willy' };

/** How the panel reads the playing track of this station, in words. */
function trackInfoText(info) {
  if (!info) return 'Not checked yet: the server checks new stations after Save';
  const sample = info.sample ? ` (now: ${info.sample})` : '';
  switch (info.kind) {
    case 'icy': return `From the stream itself (ICY titles)${sample}`;
    case 'provider': return `From the ${PROVIDERS[info.provider] || info.provider} API${sample}`;
    case 'icecast': return `From the Icecast server status${sample}`;
    case 'shoutcast': return `From the Shoutcast server${sample}`;
    case 'json': return `From ${hostOf(info.url)}${sample}`;
    default: return 'No track info found: the canvas shows the station name';
  }
}

function TrackInfoLine({ station, onDetected }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const saved = !!station.track_info || station.url === station.savedUrl;
  const detect = async () => {
    setBusy(true);
    setError(null);
    try { onDetected(await api('POST', '/stations/detect', { url: station.url })); }
    catch (e) { setError(e.message); }
    setBusy(false);
  };
  return (
    <div className="track-info">
      <span className={station.track_info?.kind === 'none' ? 'error' : 'muted'}>
        {busy ? 'Checking the stream, the server and the homepage… (up to a minute)' : error || trackInfoText(station.track_info)}
      </span>
      {saved && station.url.trim() && (
        <button type="button" className="btn ghost small" disabled={busy} onClick={detect}>
          <Icon.refresh /> Detect again
        </button>
      )}
    </div>
  );
}

function StationRow({ station, art, index, count, groupIndex, groups, open, onToggle,
                      onChange, onMove, onMoveTo, onDelete }) {
  const bad = (field) => (station.touched && !(field === 'name' ? station.name.trim() : URL_RE.test(station.url.trim())));
  const ok = stationOk(station);
  return (
    <li className={`edit-station ${open ? 'is-open' : ''}`}>
      <div className="edit-summary">
        <Thumb src={(station.image || '').trim() || art || somafmLogo(station.url)} name={station.name} />
        <div className="edit-label">
          <strong>{station.name || 'New station'}</strong>
          <span className={ok ? '' : 'is-bad'}>{ok ? hostOf(station.url) : 'Needs a name and a stream URL'}</span>
        </div>
        <IconButton label="Move up" disabled={index === 0} onClick={() => onMove(-1)}><Icon.up /></IconButton>
        <IconButton label="Move down" disabled={index === count - 1} onClick={() => onMove(1)}><Icon.down /></IconButton>
        <IconButton label={open ? 'Close' : 'Edit'} onClick={onToggle}>{open ? <Icon.check /> : <Icon.edit />}</IconButton>
      </div>
      {open && (
      <div className="edit-fields">
        <input className={`input ${bad('name') ? 'is-bad' : ''}`} placeholder="Station name" value={station.name}
               maxLength={60} onChange={(e) => onChange({ name: e.target.value })} />
        <input className={`input mono small ${bad('url') ? 'is-bad' : ''}`} placeholder="https://… stream URL"
               value={station.url} onChange={(e) => onChange({ url: e.target.value, track_info: undefined })} />
        <input className={`input mono small ${imageOk(station) ? '' : 'is-bad'}`}
               placeholder="Logo URL (optional; replaces the found logo)"
               value={station.image || ''} onChange={(e) => onChange({ image: e.target.value })} />
        <TrackInfoLine station={station} onDetected={(info) => onChange({ track_info: info })} />
        <div className="edit-more">
          <label className="group-select select">
            <span>Group</span>
            <select value={groupIndex} onChange={(e) => onMoveTo(Number(e.target.value))}>
              {groups.map((g, gi) => <option key={g.key} value={gi}>{g.name || 'Unnamed group'}</option>)}
            </select>
          </label>
          <button type="button" className="btn ghost small danger-text" onClick={onDelete}>
            <Icon.trash /> Delete
          </button>
        </div>
      </div>
      )}
    </li>
  );
}

export default function StationEditor({ stations, onSaved, onClose }) {
  const [groups, setGroups] = useState(() => withKeys(stations.groups || []));
  const [confirm, setConfirm] = useState(null); // group key awaiting delete, or 'discard'
  const [state, setState] = useState(null); // 'busy' | error text
  const [openKey, setOpenKey] = useState(null); // the station row with open fields
  const [art, setArt] = useState({});

  useEffect(() => {
    api('GET', '/audio/station-art').then((s) => {
      setArt(Object.fromEntries((s.entries || []).filter((e) => e.art_url).map((e) => [e.stream_url, e.art_url])));
    }).catch(() => {});
  }, []);

  // track_info is saved by the server itself (detection), so it is no edit
  const comparable = (gs) => JSON.stringify(gs.map((g) => ({ ...g, stations: g.stations.map((s) => omit(s, 'track_info')) })));
  const original = useMemo(() => comparable(stations.groups || []), [stations]);
  const clean = withoutKeys(groups).map((g) => ({
    ...g, name: g.name.trim(),
    stations: g.stations.map((s) => {
      const out = { ...s, name: s.name.trim(), url: s.url.trim() };
      const image = (s.image || '').trim();
      if (image) out.image = image; else delete out.image;
      return out;
    }),
  }));
  const dirty = comparable(clean) !== original;
  const valid = clean.every((g) => g.name && g.stations.every(stationOk));
  const total = clean.reduce((n, g) => n + g.stations.length, 0);

  const updateGroup = (gi, fn) => setGroups((gs) => gs.map((g, i) => (i === gi ? fn(g) : g)));
  const updateStation = (gi, si, patch) => updateGroup(gi, (g) => ({
    ...g, stations: g.stations.map((s, i) => (i === si ? { ...s, ...patch, touched: true } : s)),
  }));
  const moveToGroup = (gi, si, target) => setGroups((gs) => {
    const station = gs[gi].stations[si];
    return gs.map((g, i) => {
      if (i === gi) return { ...g, stations: g.stations.filter((_, j) => j !== si) };
      if (i === target) return { ...g, stations: [...g.stations, station] };
      return g;
    });
  });

  const save = async () => {
    setState('busy');
    try {
      onSaved(await api('PUT', '/stations', { groups: clean }));
      onClose();
    } catch (e) {
      setState(e.message);
    }
  };

  const close = () => {
    if (dirty && confirm !== 'discard') { setConfirm('discard'); return; }
    onClose();
  };

  return (
    <div className="editor">
      <div className="editor-head">
        <div>
          <h2 className="editor-title">Radio stations</h2>
          <p className="muted">{groups.length} groups · {total} stations. Changes apply when you save.</p>
        </div>
      </div>

      {groups.map((group, gi) => (
        <section key={group.key} className="edit-group">
          <div className="edit-group-head">
            <input className={`input group-name ${group.name.trim() ? '' : 'is-bad'}`} value={group.name}
                   placeholder="Group name" maxLength={40}
                   onChange={(e) => updateGroup(gi, (g) => ({ ...g, name: e.target.value }))} />
            <IconButton label="Move group up" disabled={gi === 0} onClick={() => setGroups((gs) => move(gs, gi, -1))}><Icon.up /></IconButton>
            <IconButton label="Move group down" disabled={gi === groups.length - 1} onClick={() => setGroups((gs) => move(gs, gi, 1))}><Icon.down /></IconButton>
            {confirm === group.key ? (
              <button type="button" className="btn stop small" onClick={() => { setGroups((gs) => gs.filter((_, i) => i !== gi)); setConfirm(null); }}>
                Delete {group.stations.length} stations?
              </button>
            ) : (
              <IconButton label="Delete group" danger
                          onClick={() => (group.stations.length ? setConfirm(group.key) : setGroups((gs) => gs.filter((_, i) => i !== gi)))}>
                <Icon.trash />
              </IconButton>
            )}
          </div>

          <ul className="edit-stations">
            {group.stations.map((station, si) => (
              <StationRow key={station.key} station={station} art={art[station.url]}
                          index={si} count={group.stations.length} groupIndex={gi} groups={groups}
                          open={openKey === station.key}
                          onToggle={() => setOpenKey((k) => (k === station.key ? null : station.key))}
                          onChange={(patch) => updateStation(gi, si, patch)}
                          onMove={(delta) => updateGroup(gi, (g) => ({ ...g, stations: move(g.stations, si, delta) }))}
                          onMoveTo={(target) => moveToGroup(gi, si, target)}
                          onDelete={() => updateGroup(gi, (g) => ({ ...g, stations: g.stations.filter((_, j) => j !== si) }))} />
            ))}
          </ul>
          <button type="button" className="btn ghost add"
                  onClick={() => {
                    const key = nextKey++;
                    updateGroup(gi, (g) => ({ ...g, stations: [...g.stations, { name: '', url: '', key }] }));
                    setOpenKey(key);
                  }}>
            <Icon.plus /> Add a station
          </button>
        </section>
      ))}

      <button type="button" className="btn ghost add wide"
              onClick={() => setGroups((gs) => [...gs, { name: '', stations: [], key: nextKey++ }])}>
        <Icon.plus /> Add a group
      </button>

      <div className="editor-bar">
        <span className={state && state !== 'busy' ? 'error' : 'muted'}>
          {state && state !== 'busy' ? state
            : !valid ? 'Every group and station needs a name, and every URL must start with http(s)://'
            : confirm === 'discard' ? 'Unsaved changes. Tap Cancel again to discard them.'
            : dirty ? 'Unsaved changes' : 'No changes'}
        </span>
        <div className="actions">
          <button type="button" className="btn ghost" onClick={close}>Cancel</button>
          <button type="button" className="btn primary" disabled={!dirty || !valid || state === 'busy'} onClick={save}>
            {state === 'busy' ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
