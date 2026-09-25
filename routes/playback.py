"""Video playback and system volume routes."""
from fastapi import APIRouter, HTTPException

from managers import system_audio
from models.request_models import PlaybackVolumeRequest, TwitchPlayRequest, YoutubePlayRequest


def _describe(duration, mute) -> str:
    duration_text = f" for {duration}s" if duration else ""
    mute_text = " (muted)" if mute else ""
    return f"{duration_text}{mute_text}"


def setup_playback_routes(playback_manager) -> APIRouter:
    router = APIRouter()

    @router.post("/playback/youtube")
    async def play_youtube_video(request: YoutubePlayRequest):
        """Play a YouTube video via browser (YouTube IFrame API)"""
        if not await playback_manager.play_youtube(request.youtube_url, request.duration, request.mute):
            raise HTTPException(status_code=400,
                                detail="Invalid YouTube URL. Please check the video URL and try again.")
        return {"message": f"Playing YouTube video{_describe(request.duration, request.mute)}"}

    @router.post("/playback/twitch")
    async def play_twitch_stream(request: TwitchPlayRequest):
        """Play a Twitch channel/VOD/clip via browser (Twitch embedded player)"""
        if not await playback_manager.play_twitch(request.twitch_url, request.duration, request.mute):
            raise HTTPException(status_code=400,
                                detail="Invalid Twitch URL. Please check the URL and try again.")
        return {"message": f"Playing Twitch stream{_describe(request.duration, request.mute)}"}

    @router.put("/playback/volume")
    async def set_playback_volume(request: PlaybackVolumeRequest):
        """Set system audio volume via PulseAudio (0-100)"""
        volume = min(100, request.volume)
        if not await system_audio.set_sink_volume(volume):
            raise HTTPException(status_code=500, detail="Failed to set volume")
        return {"volume": volume}

    @router.get("/playback/volume")
    async def get_playback_volume():
        """Get current system audio volume"""
        return {"volume": await system_audio.get_sink_volume()}

    @router.delete("/playback/stop")
    async def stop_playback():
        """Stop current playback"""
        if not await playback_manager.stop_playback():
            raise HTTPException(status_code=500, detail="Failed to stop playback")
        return {"message": "Playback stopped"}

    @router.get("/playback/status")
    async def get_playback_status():
        """Get current playback status"""
        return playback_manager.get_playback_status()

    return router
