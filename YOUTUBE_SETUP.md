# YouTube Authentication Setup

YouTube requires authentication to prevent bot access. This guide shows how to enable YouTube playback using browser cookies.

## Quick Setup

### 1. Export Cookies from Your Browser

**Firefox (Recommended):**
1. Install extension: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)
2. Visit https://www.youtube.com
3. Optional: Log in with a Google account (or stay logged out for basic access)
4. Click the cookies.txt extension icon
5. Click "Export" → Save as `cookies.txt`

**Chrome/Chromium:**
1. Install extension: "Get cookies.txt LOCALLY"
2. Visit https://www.youtube.com
3. Optional: Log in with a Google account
4. Click extension icon → Export cookies

### 2. Transfer Cookies to Pi

From your computer, copy the file to the Pi:

```bash
scp ~/Downloads/cookies.txt hsg@<your-pi-ip>:/home/hsg/srs_server/youtube-cookies.txt
```

Or if you're already SSH'd into the Pi:
```bash
# On your computer, run:
cat cookies.txt | ssh hsg@<pi-ip> 'cat > /home/hsg/srs_server/youtube-cookies.txt'
```

### 3. Restart the Service

```bash
sudo systemctl restart hsg-canvas
```

### 4. Test YouTube Playback

The system will automatically detect the cookies file and use it for YouTube authentication.

## Security Considerations

### For Public/Shared Pi (Recommended):
- **Don't use your personal Google account**
- Create a burner/throwback Google account specifically for this Pi
- Or use cookies without logging in (limited access but safer)

### For Private Pi:
- You can use your personal account cookies
- Cookies expire and may need refreshing every few months

## Troubleshooting

**Still getting "Sign in to confirm you're not a bot" error:**
- Check file location: `/home/hsg/srs_server/youtube-cookies.txt`
- Check file permissions: `chmod 644 youtube-cookies.txt`
- Check logs: `sudo journalctl -u hsg-canvas -f | grep -i youtube`
- Try refreshing cookies (export again from browser)

**Cookies expire:**
- YouTube cookies typically last 6-12 months
- Re-export and replace the file when they expire
- You'll see "Sign in" errors when cookies are expired

## Without Cookies

Without cookies, YouTube access is limited:
- Most popular videos will be blocked
- Some videos may still work
- Error: "Sign in to confirm you're not a bot"

The system will work fine for:
- Spotify playback ✅
- Radio streams (SomaFM, etc.) ✅
- Chromecast ✅
- Images/QR codes ✅
- Direct video URLs ✅

## File Location

The cookies file must be at:
```
/home/hsg/srs_server/youtube-cookies.txt
```

The system automatically detects this file and uses it if present.
