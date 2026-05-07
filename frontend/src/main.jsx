import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Opt-in compositor-keepalive: only the primary Pi 4's cage kiosk needs the
// always-on animation that forces continuous frame callbacks. Weaker hardware
// (Pi 3B+) gets it disabled by default — pass ?keepalive=1 to enable.
if (new URLSearchParams(window.location.search).get('keepalive') === '1') {
  document.documentElement.classList.add('keepalive')
}

createRoot(document.getElementById('root')).render(
  <App />,
)
