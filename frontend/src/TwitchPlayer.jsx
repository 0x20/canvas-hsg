import './TwitchPlayer.css';

/**
 * TwitchPlayer - Fullscreen Twitch channel / VOD / clip via the embedded player.
 *
 * Twitch's iframe requires a `parent` query param naming the host that embeds
 * it; we use the current hostname so it works whether the kiosk loads via
 * 127.0.0.1, localhost, or the Pi's LAN name. Plays with sound unless the
 * backend marks the item muted.
 */
export default function TwitchPlayer({ item }) {
  const kind = item?.content?.kind || 'channel';
  const id = item?.content?.twitch_id || '';
  const mute = item?.content?.mute || false;

  if (!id) return <div className="twitch-player" />;

  // `parent` must be the bare hostname (no scheme, no port).
  const parent = window.location.hostname;
  const muted = mute ? 'true' : 'false';

  let src;
  if (kind === 'clip') {
    src = `https://clips.twitch.tv/embed?clip=${encodeURIComponent(id)}&parent=${parent}&autoplay=true&muted=${muted}`;
  } else if (kind === 'video') {
    src = `https://player.twitch.tv/?video=${encodeURIComponent(id)}&parent=${parent}&autoplay=true&muted=${muted}`;
  } else {
    src = `https://player.twitch.tv/?channel=${encodeURIComponent(id)}&parent=${parent}&autoplay=true&muted=${muted}`;
  }

  return (
    <div className="twitch-player">
      <iframe
        className="twitch-iframe"
        src={src}
        title="Twitch player"
        allow="autoplay; fullscreen"
        allowFullScreen
        frameBorder="0"
      />
    </div>
  );
}
