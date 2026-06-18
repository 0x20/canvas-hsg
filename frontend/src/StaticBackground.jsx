import { useEffect, useState } from 'react';
import QRCode from 'qrcode';
import './StaticBackground.css';

/**
 * Static Background - Default display when nothing is playing.
 *
 * The artwork is a clean image; the hackerspace logo and a QR code are drawn
 * as DOM overlays (not baked in) so they can be toggled off and sit inside an
 * overscan-safe inset — baked-in corner elements get clipped by object-fit
 * cover + TV overscan. Toggles and the QR target come from the display base
 * content (item.content), set by the BackgroundManager.
 */
export default function StaticBackground({ item }) {
  const content = item?.content || {};
  const backgroundUrl = content.background_url || '/static/canvas_background_2.png';
  const showLogo = content.show_logo !== false; // default on
  const showQr = content.show_qr !== false;
  const qrUrl = content.qr_url || '';

  const [qrDataUrl, setQrDataUrl] = useState('');

  useEffect(() => {
    if (!showQr || !qrUrl) {
      setQrDataUrl('');
      return;
    }
    QRCode.toDataURL(qrUrl, {
      width: 256,
      margin: 2,
      // Light modules at 50% alpha so the QR blends into the artwork instead of
      // sitting in an opaque white box. High error-correction compensates for
      // the reduced contrast so it still scans.
      errorCorrectionLevel: 'H',
      color: { dark: '#000000', light: '#ffffff80' },
    }).then(setQrDataUrl).catch(() => setQrDataUrl(''));
  }, [showQr, qrUrl]);

  return (
    <div className="static-background">
      <img src={backgroundUrl} alt="" className="background-image" />
      <div className="overlay-title">CANVAS</div>
      {showLogo && (
        <img src="/static/hsg_logo_overlay.png" alt="" className="overlay-logo" />
      )}
      {showQr && qrDataUrl && (
        <img src={qrDataUrl} alt="" className="overlay-qr" />
      )}
    </div>
  );
}
