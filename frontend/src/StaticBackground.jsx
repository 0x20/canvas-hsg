import './StaticBackground.css';

/**
 * Static Background - Default display when nothing is playing
 * Shows original canvas background image
 */
export default function StaticBackground() {
  return (
    <div className="static-background">
      <img
        src="/static/canvas_background.png"
        alt="Canvas Background"
        className="background-image"
      />
    </div>
  );
}
