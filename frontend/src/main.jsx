import { createRoot } from 'react-dom/client'
import { lazy, Suspense } from 'react'
import './index.css'
import App from './App.jsx'

// Opt-in compositor-keepalive: only the primary Pi 4's cage kiosk needs the
// always-on animation that forces continuous frame callbacks. Weaker hardware
// (Pi 3B+) gets it disabled by default — pass ?keepalive=1 to enable.
if (new URLSearchParams(window.location.search).get('keepalive') === '1') {
  document.documentElement.classList.add('keepalive')
}

// The server serves this bundle at / (the control panel) and at /canvas/ (the
// display). ?view=control forces the panel under /canvas/ too.
const isControl = !window.location.pathname.startsWith('/canvas') ||
  new URLSearchParams(window.location.search).get('view') === 'control'
const Control = isControl ? lazy(() => import('./control/Control.jsx')) : null
if (!isControl) document.documentElement.classList.add('is-display')

createRoot(document.getElementById('root')).render(
  Control
    ? <Suspense fallback={null}><Control /></Suspense>
    : <App />,
)
