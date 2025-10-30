"""
MPV Pool Health Monitor

Background task that periodically checks and restarts MPV processes.
"""
import asyncio
import logging

from core.mpv_pools import AudioMPVPool, VideoMPVPool
from config import HEALTH_CHECK_INTERVAL


async def mpv_pool_health_monitor(audio_pool: AudioMPVPool, video_pool: VideoMPVPool):
    """Background task that periodically checks and restarts both audio and video MPV pools"""
    logging.info("MPV Pool Health Monitor started (monitoring audio and video pools)")

    while True:
        try:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

            # Check audio pool
            if audio_pool and len(audio_pool.processes) > 0:
                audio_health = await audio_pool.health_check()

                # Only log if there were issues
                if audio_health["restarted"] > 0 or audio_health["failed"] > 0:
                    logging.warning(f"Audio Pool Health: {audio_health['healthy']} healthy, "
                                  f"{audio_health['restarted']} restarted, "
                                  f"{audio_health['failed']} failed")

            # Check video pool
            if video_pool and len(video_pool.processes) > 0:
                video_health = await video_pool.health_check()

                # Only log if there were issues
                if video_health["restarted"] > 0 or video_health["failed"] > 0:
                    logging.warning(f"Video Pool Health: {video_health['healthy']} healthy, "
                                  f"{video_health['restarted']} restarted, "
                                  f"{video_health['failed']} failed")

        except asyncio.CancelledError:
            logging.info("MPV Pool Health Monitor stopped")
            break
        except Exception as e:
            logging.error(f"Error in MPV pool health monitor: {e}")
            # Continue monitoring even if there's an error
            await asyncio.sleep(5)
