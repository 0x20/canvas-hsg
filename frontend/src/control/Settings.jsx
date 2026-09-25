import { useEffect, useRef, useState } from 'react';
import { api } from './api';
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
      {overlays?.background_url && (
        <div className="preview" style={{ backgroundImage: `url("${overlays.background_url}")` }} />
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

function SpotifyVolume() {
  const [status, setStatus] = useState(null);
  const pending = useRef(null);
  useEffect(() => { api('GET', '/audio/spotify/status').then(setStatus).catch(() => {}); }, []);
  const change = (v) => {
    setStatus((s) => ({ ...s, volume: v }));
    clearTimeout(pending.current);
    pending.current = setTimeout(() => api('PUT', '/audio/spotify/volume', { volume: v }).catch(() => {}), 150);
  };
  return (
    <Card icon={<Icon.speaker />} title="Spotify Connect">
      <p className="muted">
        {status ? (status.service_running ? `Ready as “${status.device_name}”` : 'The Raspotify service is not running') : '…'}
      </p>
      <label className="volume">
        <span className="volume-lbl">Output level</span>
        <input type="range" min="0" max="100" value={status?.volume ?? 0} disabled={!status}
               style={{ '--fill': `${status?.volume ?? 0}%` }} onChange={(e) => change(Number(e.target.value))} />
        <span className="volume-val mono">{status?.volume ?? '–'}</span>
      </label>
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
    Promise.all([get('/health'), get('/sendspin/status'), get('/bluetooth/status'), get('/ws/status')])
      .then(([health, sendspin, bluetooth, ws]) => setInfo({ health, sendspin, bluetooth, ws }));
  }, []);
  const { health, sendspin, bluetooth, ws } = info;
  const rows = [
    ['Version', health?.version],
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
        <a className="btn ghost" href="/canvas/" target="_blank" rel="noreferrer">Open the canvas</a>
      </div>
    </Card>
  );
}

export default function Settings({ pin }) {
  return (
    <div className="settings">
      <IdleScreen />
      <SpotifyVolume />
      <Tv />
      <Cast />
      <System pin={pin} />
    </div>
  );
}
