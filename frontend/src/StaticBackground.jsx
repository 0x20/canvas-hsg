import './StaticBackground.css';

/**
 * Static Background - Default display when nothing is playing
 * Shows original canvas background image (includes logo + QR code)
 */
export default function StaticBackground({ item }) {
  const backgroundUrl = item?.content?.background_url || '/static/canvas_background.png';

  return (
    <div className="static-background">
      <img
        src={backgroundUrl}
        alt="Canvas Background"
        className="background-image"
      />
    </div>
  );
}
