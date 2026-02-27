import { useState, useEffect } from 'react';
import './ImageDisplay.css';

/**
 * ImageDisplay - Fullscreen image/QR code display with optional duration progress bar
 */
export default function ImageDisplay({ item }) {
  const [progress, setProgress] = useState(0);
  const imageUrl = item?.content?.image_url || '';
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
      <img
        src={imageUrl}
        alt="Display"
        className="display-image"
      />
      {duration > 0 && (
        <div className="image-progress-container">
          <div className="image-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  );
}
