import { useState, useEffect } from 'react';
import './ImageDisplay.css';

/**
 * ImageDisplay - Fullscreen image/QR code display with optional duration progress bar
 */
export default function ImageDisplay({ item }) {
  const [progress, setProgress] = useState(0);
  const imageUrl = item?.content?.image_url || '';
  // Station art sets blurred_bg to get the now-playing look (blurred
  // screen-filling backdrop + enlarged cover); QR codes/plain images don't.
  const blurredBg = !!item?.content?.blurred_bg;
  const duration = item?.duration;
  const pushedAt = item?.pushed_at;

  useEffect(() => {
    if (!duration || !pushedAt) return;

    const interval = setInterval(() => {
      const elapsed = Date.now() / 1000 - pushedAt;
      const pct = Math.min(100, (elapsed / duration) * 100);
      setProgress(pct);
      if (pct >= 100) clearInterval(interval);
    }, 100);

    return () => clearInterval(interval);
  }, [duration, pushedAt]);

  return (
    <div className="image-display">
      {blurredBg && imageUrl && (
        <div
          className="image-background-blur"
          style={{ backgroundImage: `linear-gradient(rgba(15,15,26,0.45),rgba(15,15,26,0.45)), url('${imageUrl}')` }}
        />
      )}
      <img
        src={imageUrl}
        alt="Display"
        className={blurredBg ? 'display-image station-art' : 'display-image'}
      />
      {duration > 0 && (
        <div className="image-progress-container">
          <div className="image-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  );
}
