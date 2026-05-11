import { createRoot, hydrateRoot } from 'react-dom/client'
import { lazy, Suspense } from 'react'
import './index.css'
import App from './App.jsx'

// Opt-in compositor-keepalive: only the primary Pi 4's cage kiosk needs the
// always-on animation that forces continuous frame callbacks. Weaker hardware
// (Pi 3B+) gets it disabled by default — pass ?keepalive=1 to enable.
if (new URLSearchParams(window.location.search).get('keepalive') === '1') {
  document.documentElement.classList.add('keepalive')
}

// Sandbox switch: load the new control surface only when explicitly requested
// via ?view=control. The kiosk path (?keepalive=1, default) keeps loading the
// existing App so on-device behavior is unaffected while we iterate.
const view = new URLSearchParams(window.location.search).get('view')
const Control = view === 'control' ? lazy(() => import('./control/Control.jsx')) : null

createRoot(document.getElementById('root')).render(
  Control
    ? <Suspense fallback={null}><Control /></Suspense>
    : <App />,
)
