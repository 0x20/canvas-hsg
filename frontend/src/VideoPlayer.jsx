import { useRef, useEffect } from 'react';
import './VideoPlayer.css';

/**
 * VideoPlayer - Fullscreen HTML5 video player
 * Plays with sound unless the backend marks the item muted.
 */
export default function VideoPlayer({ item }) {
  const videoRef = useRef(null);
  const videoUrl = item?.content?.video_url || '';
  const mute = item?.content?.mute || false;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const handleEnded = () => {
      // Video finished — tell backend to pop from stack
      fetch(`/display/${item.id}`, { method: 'DELETE' }).catch(() => {});
    };

    video.addEventListener('ended', handleEnded);
    return () => video.removeEventListener('ended', handleEnded);
  }, [item?.id]);

  return (
    <div className="video-player">
      <video
        ref={videoRef}
        src={videoUrl}
        autoPlay
        muted={mute}
        className="video-element"
      />
    </div>
  );
}
