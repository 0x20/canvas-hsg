import './WebsiteFrame.css';

/**
 * WebsiteFrame - Fullscreen iframe for arbitrary URLs
 * Supports optional zoom via CSS transform.
 */
export default function WebsiteFrame({ item }) {
  const url = item?.content?.url || '';
  const zoom = item?.content?.zoom || 1;

  return (
    <div className="website-frame">
      <iframe
        src={url}
        className="website-iframe"
        style={{
          transform: zoom !== 1 ? `scale(${zoom})` : undefined,
          transformOrigin: zoom !== 1 ? 'top left' : undefined,
          width: zoom !== 1 ? `${100 / zoom}%` : '100%',
          height: zoom !== 1 ? `${100 / zoom}%` : '100%',
        }}
        title="Website Display"
        sandbox="allow-scripts allow-same-origin allow-popups"
      />
    </div>
  );
}
