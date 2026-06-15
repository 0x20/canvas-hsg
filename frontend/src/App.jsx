import { useState, useEffect } from 'react';
import './App.css';
import useWebSocket from './useWebSocket';
import NowPlaying from './NowPlaying';
import StaticBackground from './StaticBackground';
import ImageDisplay from './ImageDisplay';
import YouTubePlayer from './YouTubePlayer';
import TwitchPlayer from './TwitchPlayer';
import WebsiteFrame from './WebsiteFrame';
import VideoPlayer from './VideoPlayer';
import AudioPlayer from './AudioPlayer';

function App() {
  const [displayItem, setDisplayItem] = useState({ type: 'static', content: {}, id: 'base' });
  const [displayStack, setDisplayStack] = useState([]);
  const [spotifySeen, setSpotifySeen] = useState(false);

  useWebSocket('/ws/display', {
    onMessage: (message) => {
      console.log('App: Received display event:', message);
      if (message.event === 'display_state') {
        setDisplayItem(message.data);
        setDisplayStack(message.data.stack || []);
        if (message.data.type === 'spotify' || message.data.type === 'sendspin' || message.data.type === 'bluetooth') {
          setSpotifySeen(true);
        }
      }
    },
  });

  // Reset spotifySeen when static becomes current (spotify was actually removed from stack)
  useEffect(() => {
    if (displayItem.type === 'static') {
      setSpotifySeen(false);
    }
  }, [displayItem.type]);

  const isNowPlayingActive = displayItem.type === 'spotify' || displayItem.type === 'sendspin' || displayItem.type === 'bluetooth';
  const keepNowPlayingMounted = spotifySeen && !isNowPlayingActive && displayItem.type !== 'static';

  // Silent overlays (image / qrcode / website) shouldn't interrupt audio when
  // a video (YouTube / Twitch) is already playing underneath. Find the most
  // recent media item in the stack; if it isn't currently the top item but
  // something silent is, keep its iframe mounted as a base layer and overlay
  // on top.
  const SILENT_OVERLAY_TYPES = ['image', 'qrcode', 'website'];
  const MEDIA_TYPES = ['youtube', 'twitch'];
  const mediaItem = [...displayStack].reverse().find((i) => MEDIA_TYPES.includes(i?.type));
  const overlayBelowMedia = mediaItem && displayItem.id !== mediaItem.id &&
                            SILENT_OVERLAY_TYPES.includes(displayItem.type);

  const renderItem = (item) => {
    switch (item.type) {
      case 'image':
      case 'qrcode':  return <ImageDisplay item={item} />;
      case 'youtube': return <YouTubePlayer item={item} />;
      case 'twitch':  return <TwitchPlayer item={item} />;
      case 'website': return <WebsiteFrame item={item} />;
      case 'video':   return <VideoPlayer item={item} />;
      case 'static':
      default:        return <StaticBackground item={item} />;
    }
  };

  const renderLayers = () => {
    if (isNowPlayingActive) return null;
    // Always wrap in .layer-base so the position in the React tree is stable
    // when a silent overlay arrives. If we conditionally added the wrapper
    // only when an overlay was present, the media component's parent would
    // change (fragment child → div child) and React would unmount/remount it,
    // destroying the iframe and briefly cutting audio — the very thing we're
    // trying to prevent.
    const baseItem = overlayBelowMedia ? mediaItem : displayItem;
    return (
      <>
        <div className="layer-base">{renderItem(baseItem)}</div>
        {overlayBelowMedia && (
          <div className="layer-overlay">{renderItem(displayItem)}</div>
        )}
      </>
    );
  };

  return (
    <>
      {(isNowPlayingActive || keepNowPlayingMounted) && <NowPlaying source={displayItem.type} />}
      {renderLayers()}
      <AudioPlayer />
    </>
  );
}

export default App;
