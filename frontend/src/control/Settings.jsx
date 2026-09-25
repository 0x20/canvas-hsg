import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import StaticBackground from '../StaticBackground';
import { Icon } from './icons';

/** A button that runs an action and shows the result for a moment. */
function ActionButton({ onRun, children, variant = 'ghost' }) {
  const [state, setState] = useState(null); // 'busy' | 'ok' | 'err'
  const click = async () => {
    setState('busy');
    try { await onRun(); setState('ok'); } catch { setState('err'); }
    setTimeout(() => setState(null), 1600);
  };
  return (
    <button className={`btn ${variant} ${state ? `is-${state}` : ''}`} disabled={state === 'busy'} onClick={click}>
      {state === 'ok' ? <Icon.check /> : null}
      {state === 'err' ? 'Failed' : children}
    </button>
  );
}

function Toggle({ label, checked, onChange }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="switch-track" /> {label}
    </label>
  );
}

function Card({ icon, title, children }) {
  return (
    <section className="card">
      <h3 className="card-title">{icon}{title}</h3>
      {children}
    </section>
  );
}

function IdleScreen() {
  const [overlays, setOverlays] = useState(null);
  const fileRef = useRef(null);
  useEffect(() => { api('GET', '/background/overlays').then(setOverlays).catch(() => {}); }, []);

  const set = (patch) => {
    setOverlays((o) => ({ ...o, ...patch }));
    api('POST', '/background/overlays', patch).then(setOverlays).catch(() => {});
  };
  const upload = async (file) => {
    const form = new FormData();
    form.append('file', file);
    await api('POST', '/background/set', form);
    setOverlays(await api('GET', '/background/overlays'));
  };

  return (
    <Card icon={<Icon.screen />} title="Idle screen">
      {/* The real idle-screen component, so the toggles show their effect */}
      {overlays && (
        <div className="preview">
          <StaticBackground item={{ content: overlays }} embedded />
        </div>
      )}
      <div className="stack">
        <Toggle label="Show the logo" checked={overlays?.show_logo} onChange={(v) => set({ show_logo: v })} />
        <Toggle label="Show the QR code to this panel" checked={overlays?.show_qr} onChange={(v) => set({ show_qr: v })} />
      </div>
      <div className="actions">
        <ActionButton onRun={() => fileRef.current.click()}><Icon.upload /> New background</ActionButton>
        <ActionButton onRun={() => api('POST', '/background/show')}>Clear the canvas</ActionButton>
      </div>
      <input ref={fileRef} type="file" accept="image/*" hidden
             onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
    </Card>
  );
}

const NAME_FIELDS = [
  ['spotify', 'Spotify Connect', 'Restarts Spotify Connect; Spotify playback stops.'],
  ['bluetooth', 'Bluetooth', 'Phones see the new name at their next scan.'],
  ['music_assistant', 'Music Assistant player', 'Restarts the player; Music Assistant playback stops.'],
];

function NameRow({ kind, label, note, value, onSaved }) {
  const [draft, setDraft] = useState(value || '');
  const [state, setState] = useState(null); // 'busy' | 'ok' | error text
  const changed = draft.trim() && draft.trim() !== (value || '');

  const save = async (e) => {
    e.preventDefault();
    setState('busy');
    try {
      onSaved(await api('PUT', '/settings/names', { kind, name: draft.trim() }));
      setState('ok');
      setTimeout(() => setState(null), 1600);
    } catch (err) {
      setState(err.message);
    }
  };

  return (
    <form className="name-row" onSubmit={save}>
      <label htmlFor={`name-${kind}`}>{label}</label>
      <div className="url-row">
        <input id={`name-${kind}`} className="input" maxLength={40} value={draft}
               placeholder={value == null ? 'Not available' : ''} disabled={value == null}
               onChange={(e) => setDraft(e.target.value)} />
        <button className={`btn ${changed ? 'primary' : 'ghost'}`} disabled={!changed || state === 'busy'}>
          {state === 'busy' ? '…' : state === 'ok' ? <><Icon.check /> Saved</> : 'Save'}
        </button>
      </div>
      {state && !['busy', 'ok'].includes(state)
        ? <p className="error">{state}</p>
        : <p className="name-note">{note}</p>}
    </form>
  );
}

function Names() {
  const [names, setNames] = useState(null);
  useEffect(() => { api('GET', '/settings/names').then(setNames).catch(() => setNames({})); }, []);
  return (
    <Card icon={<Icon.tag />} title="Names">
      <p className="muted">The names phones and Music Assistant show for the canvas.</p>
      {names && NAME_FIELDS.map(([kind, label, note]) => (
        <NameRow key={kind} kind={kind} label={label} note={note} value={names[kind]} onSaved={setNames} />
      ))}
    </Card>
  );
}

function Cast() {
  const [devices, setDevices] = useState([]);
  const [device, setDevice] = useState('');
  const [url, setUrl] = useState('');
  const [status, setStatus] = useState(null);

  const applyTargets = (data) => {
    const casts = (data.targets || []).filter((t) => String(t.type).includes('chromecast'));
    setDevices(casts);
    setDevice((d) => d || casts[0]?.metadata?.device_name || '');
  };
  const load = async () => {
    applyTargets(await api('GET', '/targets'));
    setStatus(await api('GET', '/chromecast/status'));
  };
  useEffect(() => {
    api('GET', '/targets').then(applyTargets).catch(() => {});
    api('GET', '/chromecast/status').then(setStatus).catch(() => {});
  }, []);

  return (
    <Card icon={<Icon.cast />} title="Cast to a Chromecast">
      {devices.length ? (
        <select className="input" value={device} onChange={(e) => setDevice(e.target.value)}>
          {devices.map((d) => <option key={d.id} value={d.metadata?.device_name}>{d.name}</option>)}
        </select>
      ) : <p className="muted">No Chromecast found on the network.</p>}
      <input className="input mono" type="url" placeholder="Media URL" value={url} onChange={(e) => setUrl(e.target.value)} />
      {status?.is_casting && <p className="muted">Casting to {status.device_name}</p>}
      <div className="actions">
        <ActionButton variant="primary" onRun={async () => {
          await api('POST', '/chromecast/start', { media_url: url, device_name: device || undefined });
          setStatus(await api('GET', '/chromecast/status'));
        }}><Icon.cast /> Cast</ActionButton>
        <ActionButton onRun={() => api('POST', '/chromecast/pause')}>Pause</ActionButton>
        <ActionButton onRun={async () => { await api('POST', '/chromecast/stop'); setStatus(await api('GET', '/chromecast/status')); }}>Stop</ActionButton>
        <ActionButton onRun={async () => { await api('POST', '/targets/refresh'); await load(); }}><Icon.refresh /> Search again</ActionButton>
      </div>
    </Card>
  );
}

function Tv() {
  const [cec, setCec] = useState(null);
  useEffect(() => { api('GET', '/cec/status').then(setCec).catch(() => {}); }, []);
  return (
    <Card icon={<Icon.tv />} title="TV and screens">
      <p className="muted">
        {cec ? (cec.available ? `TV power: ${cec.tv_power?.power_status || 'unknown'}` : 'HDMI-CEC is not available on this Pi') : '…'}
      </p>
      <div className="actions">
        {cec?.available && <ActionButton onRun={() => api('POST', '/cec/tv/power-on')}>TV on</ActionButton>}
        {cec?.available && <ActionButton onRun={() => api('POST', '/cec/tv/power-off')}>TV off</ActionButton>}
        <ActionButton onRun={() => api('POST', '/display/reload')}><Icon.refresh /> Reload the TV page</ActionButton>
        <ActionButton onRun={() => api('POST', '/display/reload-clients')}><Icon.refresh /> Reload all screens</ActionButton>
      </div>
    </Card>
  );
}

function System({ pin }) {
  const [info, setInfo] = useState({});
  useEffect(() => {
    const get = (p) => api('GET', p).catch(() => null);
    Promise.all([get('/health'), get('/audio/spotify/status'), get('/sendspin/status'),
                 get('/bluetooth/status'), get('/ws/status')])
      .then(([health, spotify, sendspin, bluetooth, ws]) => setInfo({ health, spotify, sendspin, bluetooth, ws }));
  }, []);
  const { health, spotify, sendspin, bluetooth, ws } = info;
  const rows = [
    ['Version', health?.version],
    ['Spotify Connect', spotify ? (spotify.service_running ? `Ready as “${spotify.device_name}”` : 'Not running') : null],
    ['Music Assistant', pin ? `Waiting for PIN ${pin}` : sendspin ? (sendspin.is_connected ? 'Connected' : 'Not connected') : null],
    ['Bluetooth', bluetooth ? (bluetooth.device_name || 'No device') : null],
    ['Open screens', ws ? `${ws.display} display, ${ws.audio} audio` : null],
  ];
  return (
    <Card icon={<Icon.gear />} title="System">
      <dl className="facts">
        {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v ?? '–'}</dd></div>)}
      </dl>
      <div className="actions">
        <a className="btn ghost" href="/docs" target="_blank" rel="noreferrer">API docs</a>
      </div>
    </Card>
  );
}

function Stations({ onEdit }) {
  return (
    <Card icon={<Icon.radio />} title="Radio stations">
      <p className="muted">Add, remove, reorder and group the stations of the Radio tab.</p>
      <div className="actions">
        <button className="btn ghost" onClick={onEdit}><Icon.edit /> Edit stations</button>
      </div>
    </Card>
  );
}

export default function Settings({ pin, onEditStations }) {
  return (
    <div className="settings">
      <IdleScreen />
      <Stations onEdit={onEditStations} />
      <Names />
      <Tv />
      <Cast />
      <System pin={pin} />
    </div>
  );
}
