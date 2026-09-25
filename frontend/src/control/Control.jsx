import { useEffect, useState } from 'react';
import '@fontsource-variable/bricolage-grotesque';
import '@fontsource/ibm-plex-mono/400.css';
import './Control.css';
import { api } from './api';
import { Icon } from './icons';
import NowCard from './NowCard';
import { RadioPicker, ScreenPicker, VideoPicker } from './Pickers';
import Settings from './Settings';
import useLive from './useLive';

const TAB_KEY = 'hsg.control.tab';
const PICKERS = [
  { id: 'radio', label: 'Radio', icon: Icon.radio },
  { id: 'video', label: 'Video', icon: Icon.video },
  { id: 'screen', label: 'Screen', icon: Icon.screen },
];

function readTab() {
  try { return localStorage.getItem(TAB_KEY) || 'radio'; } catch { return 'radio'; }
}

function PairingBanner({ pin }) {
  if (!pin) return null;
  return (
    <aside className="pairing" role="status">
      <Icon.key />
      <div>
        <p className="pairing-lead">Music Assistant asks to pair the canvas</p>
        <p className="pairing-help">Enter this PIN in Music Assistant</p>
      </div>
      <span className="pairing-pin mono">{pin}</span>
    </aside>
  );
}

function Space() {
  const [state, setState] = useState(null);
  const run = async (script) => {
    setState(`${script}:busy`);
    try {
      await api('POST', `/ha/script/${script}`);
      setState(`${script}:ok`);
    } catch {
      setState(`${script}:err`);
    }
    setTimeout(() => setState(null), 2000);
  };
  const label = (script, text) => ({
    [`${script}:busy`]: '…', [`${script}:ok`]: 'Done', [`${script}:err`]: 'Failed',
  }[state] || text);
  return (
    <section className="space" aria-label="The space">
      <h2 className="section-title">The space</h2>
      <div className="space-buttons">
        <button className="space-btn open" onClick={() => run('open_space')}>
          <Icon.door /> {label('open_space', 'Open the space')}
        </button>
        <button className="space-btn close" onClick={() => run('close_space')}>
          <Icon.lock /> {label('close_space', 'Close the space')}
        </button>
      </div>
    </section>
  );
}

export default function Control() {
  const { display, track, pin, online } = useLive();
  const [view, setView] = useState('home');
  const [picker, setPicker] = useState(readTab);
  const [sources, setSources] = useState({});

  useEffect(() => {
    document.title = 'HSG Canvas';
    api('GET', '/media-sources').then(setSources).catch(() => {});
  }, []);

  const choose = (id) => {
    setPicker(id);
    try { localStorage.setItem(TAB_KEY, id); } catch { /* private mode */ }
  };

  return (
    <div className="control">
      <header className="top">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">HSG Canvas</span>
        </div>
        <nav className="views">
          <button className={view === 'home' ? 'is-on' : ''} onClick={() => setView('home')} aria-label="Remote">
            <Icon.home />
          </button>
          <button className={view === 'settings' ? 'is-on' : ''} onClick={() => setView('settings')} aria-label="Settings">
            <Icon.gear />
          </button>
        </nav>
      </header>

      {online === false && (
        <div className="offline" role="status">Lost the connection to the canvas. Reconnecting…</div>
      )}

      <main className="main">
        <PairingBanner pin={pin} />
        {view === 'home' ? (
          <>
            <NowCard display={display} track={track} />
            <Space />
            <section className="play" aria-label="Play something">
              <div className="segmented big" role="tablist">
                {PICKERS.map((p) => (
                  <button key={p.id} role="tab" aria-selected={picker === p.id}
                          className={picker === p.id ? 'is-on' : ''} onClick={() => choose(p.id)}>
                    <p.icon /> {p.label}
                  </button>
                ))}
              </div>
              {picker === 'radio' && <RadioPicker sources={sources} display={display} />}
              {picker === 'video' && <VideoPicker sources={sources} display={display} />}
              {picker === 'screen' && <ScreenPicker />}
            </section>
          </>
        ) : (
          <Settings pin={pin} />
        )}
      </main>
    </div>
  );
}
