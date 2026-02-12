# HSG Canvas - React Frontend with Hot Reload

This directory contains the React-based now-playing display with hot module replacement (HMR).

## Features

- **React Components**: Modern React with hooks (useState, useEffect, useRef)
- **Hot Reload**: Edit CSS/JS and see changes instantly without Chromium restart
- **WebSocket Integration**: Real-time track updates from Spotify
- **Scrolling Text Animations**: Automatic overflow detection and scrolling
- **Blurred Album Art Background**: Dynamic background with 20px blur

## Quick Start

Use the startup script to run both servers:

```bash
cd /home/hsg/srs_server
./start-with-react.sh
```

This script:
1. Starts Vite dev server on port 5173
2. Starts FastAPI server on port 80
3. Chromium kiosk mode points to http://127.0.0.1:5173

Now you can edit `src/NowPlaying.css` or `src/NowPlaying.jsx` and see changes instantly!

## Customization Examples

### Change Blur Amount

Edit `src/NowPlaying.css`:
```css
.background {
  filter: blur(20px); /* Change this value (default: 20px) */
}
```

### Change Font Sizes

Edit `src/NowPlaying.css`:
```css
.track-name {
  font-size: 8vw; /* Track name size */
}

.artist-name {
  font-size: 5vw; /* Artist name size */
}
```

## File Structure

```
frontend/
├── src/
│   ├── App.jsx              # Main app component
│   ├── NowPlaying.jsx       # Now-playing display component
│   ├── NowPlaying.css       # Styles with animations
│   ├── index.css            # Global styles (cursor hidden, reset)
│   └── main.jsx             # React entry point
├── index.html               # HTML template with Google Fonts
├── vite.config.js           # Vite configuration (port 5173, CORS)
└── package.json             # Dependencies
```

## Dependencies

- React 18.3.1
- Vite 5.4.21 (Node.js 18 compatible)
- @vitejs/plugin-react 4.3.4
