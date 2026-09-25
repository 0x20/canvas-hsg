import { useMemo, useState } from 'react';
import { api } from './api';
import { Icon } from './icons';

let nextKey = 1;
const withKeys = (groups) => groups.map((g) => ({
  ...g, key: nextKey++, stations: g.stations.map((s) => ({ ...s, key: nextKey++ })),
}));
/** A copy of obj without the given fields. */
const omit = (obj, ...fields) => Object.fromEntries(Object.entries(obj).filter(([k]) => !fields.includes(k)));

// The editor-only fields: React keys and the "user typed here" flag
const withoutKeys = (groups) => groups.map((g) => ({
  ...omit(g, 'key', 'stations'),
  stations: g.stations.map((s) => omit(s, 'key', 'touched')),
}));

const URL_RE = /^https?:\/\/\S+$/;
const stationOk = (s) => s.name.trim() && URL_RE.test(s.url.trim());

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

function StationRow({ station, index, count, groupIndex, groups, onChange, onMove, onMoveTo, onDelete }) {
  const bad = (field) => (station.touched && !(field === 'name' ? station.name.trim() : URL_RE.test(station.url.trim())));
  return (
    <li className="edit-station">
      <div className="edit-fields">
        <input className={`input ${bad('name') ? 'is-bad' : ''}`} placeholder="Station name" value={station.name}
               maxLength={60} onChange={(e) => onChange({ name: e.target.value })} />
        <input className={`input mono small ${bad('url') ? 'is-bad' : ''}`} placeholder="https://… stream URL"
               value={station.url} onChange={(e) => onChange({ url: e.target.value })} />
      </div>
      <div className="edit-tools">
        <IconButton label="Move up" disabled={index === 0} onClick={() => onMove(-1)}><Icon.up /></IconButton>
        <IconButton label="Move down" disabled={index === count - 1} onClick={() => onMove(1)}><Icon.down /></IconButton>
        <label className="group-select" title="Move to another group">
          <span className="sr-only">Group</span>
          <select value={groupIndex} onChange={(e) => onMoveTo(Number(e.target.value))}>
            {groups.map((g, gi) => <option key={g.key} value={gi}>{g.name || 'Unnamed group'}</option>)}
          </select>
        </label>
        <IconButton label="Delete station" danger onClick={onDelete}><Icon.trash /></IconButton>
      </div>
    </li>
  );
}

export default function StationEditor({ stations, onSaved, onClose }) {
  const [groups, setGroups] = useState(() => withKeys(stations.groups || []));
  const [confirm, setConfirm] = useState(null); // group key awaiting delete, or 'discard'
  const [state, setState] = useState(null); // 'busy' | error text

  const original = useMemo(() => JSON.stringify(stations.groups || []), [stations]);
  const clean = withoutKeys(groups).map((g) => ({
    ...g, name: g.name.trim(),
    stations: g.stations.map((s) => ({ ...s, name: s.name.trim(), url: s.url.trim() })),
  }));
  const dirty = JSON.stringify(clean) !== original;
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
              <StationRow key={station.key} station={station} index={si} count={group.stations.length}
                          groupIndex={gi} groups={groups}
                          onChange={(patch) => updateStation(gi, si, patch)}
                          onMove={(delta) => updateGroup(gi, (g) => ({ ...g, stations: move(g.stations, si, delta) }))}
                          onMoveTo={(target) => moveToGroup(gi, si, target)}
                          onDelete={() => updateGroup(gi, (g) => ({ ...g, stations: g.stations.filter((_, j) => j !== si) }))} />
            ))}
          </ul>
          <button type="button" className="btn ghost add"
                  onClick={() => updateGroup(gi, (g) => ({ ...g, stations: [...g.stations, { name: '', url: '', key: nextKey++ }] }))}>
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
            : !valid ? 'Every group and station needs a name and a valid http(s) URL'
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
