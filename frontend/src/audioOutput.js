// Only the audio-output display (the Pi kiosk, launched with ?audio=1) plays
// sound and reports playback to the backend. Every other screen loading
// /canvas is a silent display-only mirror: if they all played, they would
// double the audio, and their reports (autoplay blocked, a different end
// time) would change the state for everyone.
export const IS_AUDIO_OUTPUT = new URLSearchParams(window.location.search).get('audio') === '1';
