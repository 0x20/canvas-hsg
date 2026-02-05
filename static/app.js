const API_BASE = '';

const POLL_INTERVALS = {
    STATUS: 10000,
    SCREEN_STREAM: 5000,
    BACKGROUND: 15000,
    CEC: 20000,
    SPOTIFY: 30000,
    OUTPUT_TARGETS: 15000
};

// Cached DOM element references
const DOM = {};

function cacheDOMElements() {
    DOM.status = document.getElementById('status');
    DOM.advancedFeatures = document.getElementById('advancedFeatures');
    DOM.toggleText = document.getElementById('toggleText');

    // Output targets
    DOM.videoTargetSelect = document.getElementById('videoTargetSelect');
    DOM.audioTargetSelect = document.getElementById('audioTargetSelect');
    DOM.videoTargetStatus = document.getElementById('videoTargetStatus');
    DOM.audioTargetStatus = document.getElementById('audioTargetStatus');

    // Stream
    DOM.streamKey = document.getElementById('streamKey');
    DOM.sourceUrl = document.getElementById('sourceUrl');
    DOM.streamProtocol = document.getElementById('streamProtocol');

    // Playback
    DOM.playbackKey = document.getElementById('playbackKey');
    DOM.player = document.getElementById('player');
    DOM.playMode = document.getElementById('playMode');
    DOM.playProtocol = document.getElementById('playProtocol');
    DOM.switchKey = document.getElementById('switchKey');

    // Video
    DOM.videoPresets = document.getElementById('videoPresets');
    DOM.customVideoUrl = document.getElementById('customVideoUrl');
    DOM.videoAudioEnabled = document.getElementById('videoAudioEnabled');
    DOM.videoDuration = document.getElementById('videoDuration');
    DOM.videoStatus = document.getElementById('videoStatus');

    // Image
    DOM.imageFile = document.getElementById('imageFile');
    DOM.imageDuration = document.getElementById('imageDuration');

    // QR Code
    DOM.qrContent = document.getElementById('qrContent');
    DOM.qrDuration = document.getElementById('qrDuration');

    // Audio
    DOM.audioStreamUrl = document.getElementById('audioStreamUrl');
    DOM.audioVolume = document.getElementById('audioVolume');
    DOM.volumeDisplay = document.getElementById('volumeDisplay');
    DOM.audioStatus = document.getElementById('audioStatus');
    DOM.quickStreamSelect = document.getElementById('quickStreamSelect');

    // Chromecast
    DOM.chromecastUrl = document.getElementById('chromecastUrl');
    DOM.chromecastDevice = document.getElementById('chromecastDevice');
    DOM.chromecastVolume = document.getElementById('chromecastVolume');
    DOM.chromecastVolumeDisplay = document.getElementById('chromecastVolumeDisplay');
    DOM.chromecastStatus = document.getElementById('chromecastStatus');

    // Cast Receiver
    DOM.castReceiverStatus = document.getElementById('castReceiverStatus');

    // Background
    DOM.backgroundFile = document.getElementById('backgroundFile');
    DOM.backgroundStatus = document.getElementById('backgroundStatus');
    DOM.staticModeBtn = document.getElementById('staticModeBtn');

    // Screen Stream
    DOM.screenStreamButton = document.getElementById('screenStreamButton');
    DOM.screenStreamStatus = document.getElementById('screenStreamStatus');
    DOM.screenStreamKey = document.getElementById('screenStreamKey');
    DOM.screenStreamProtocol = document.getElementById('screenStreamProtocol');

    // System
    DOM.systemStats = document.getElementById('systemStats');
    DOM.activeStreams = document.getElementById('activeStreams');
    DOM.currentPlayback = document.getElementById('currentPlayback');
    DOM.resolutionDisplay = document.getElementById('resolution-display');

    // CEC
    DOM.cecAvailability = document.getElementById('cecAvailability');
    DOM.tvPowerStatus = document.getElementById('tvPowerStatus');
    DOM.tvAddress = document.getElementById('tvAddress');
    DOM.tvPowerOnBtn = document.getElementById('tvPowerOnBtn');
    DOM.tvPowerOffBtn = document.getElementById('tvPowerOffBtn');

    // Webcast
    DOM.webcastUrl = document.getElementById('webcastUrl');
    DOM.viewportSize = document.getElementById('viewportSize');
    DOM.scrollDelay = document.getElementById('scrollDelay');
    DOM.scrollPercentage = document.getElementById('scrollPercentage');
    DOM.overlapPercentage = document.getElementById('overlapPercentage');
    DOM.loopCount = document.getElementById('loopCount');
    DOM.webcastStartBtn = document.getElementById('webcastStartBtn');
    DOM.webcastStopBtn = document.getElementById('webcastStopBtn');
    DOM.webcastState = document.getElementById('webcastState');

    // Spotify
    DOM.spotifyServiceStatus = document.getElementById('spotifyServiceStatus');
    DOM.spotifyPlaybackInfo = document.getElementById('spotifyPlaybackInfo');
    DOM.spotifyTrackId = document.getElementById('spotifyTrackId');
    DOM.spotifyDuration = document.getElementById('spotifyDuration');
    DOM.spotifyLastEvent = document.getElementById('spotifyLastEvent');

    // Action buttons
    DOM.playVideoBtn = document.getElementById('playVideoBtn');
    DOM.stopVideoBtn = document.getElementById('stopVideoBtn');
    DOM.startAudioBtn = document.getElementById('startAudioBtn');
    DOM.stopAudioBtn = document.getElementById('stopAudioBtn');
    DOM.discoverChromecastBtn = document.getElementById('discoverChromecastBtn');
    DOM.startChromecastBtn = document.getElementById('startChromecastBtn');
    DOM.pauseChromecastBtn = document.getElementById('pauseChromecastBtn');
    DOM.stopChromecastBtn = document.getElementById('stopChromecastBtn');
    DOM.startPlaybackBtn = document.getElementById('startPlaybackBtn');
    DOM.stopPlaybackBtn = document.getElementById('stopPlaybackBtn');
    DOM.startStreamBtn = document.getElementById('startStreamBtn');
    DOM.displayImageBtn = document.getElementById('displayImageBtn');
    DOM.stopDisplayImageBtn = document.getElementById('stopDisplayImageBtn');
    DOM.displayQRCodeBtn = document.getElementById('displayQRCodeBtn');
    DOM.stopQRCodeBtn = document.getElementById('stopQRCodeBtn');
    DOM.setBackgroundBtn = document.getElementById('setBackgroundBtn');
    DOM.refreshBackgroundBtn = document.getElementById('refreshBackgroundBtn');
    DOM.showBackgroundBtn = document.getElementById('showBackgroundBtn');
    DOM.refreshStatusBtn = document.getElementById('refreshStatusBtn');
    DOM.switchStreamBtn = document.getElementById('switchStreamBtn');
    DOM.switchPlayerMpvBtn = document.getElementById('switchPlayerMpvBtn');
    DOM.switchPlayerFfplayBtn = document.getElementById('switchPlayerFfplayBtn');
    DOM.toggleAdvancedBtn = document.getElementById('toggleAdvancedBtn');
    DOM.refreshSpotifyBtn = document.getElementById('refreshSpotifyBtn');
    DOM.refreshCECBtn = document.getElementById('refreshCECBtn');
}

// Tab switching
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    document.getElementById('tab-' + tabName).classList.add('active');
    document.getElementById('tab-btn-' + tabName).classList.add('active');
}

// Toggle advanced features visibility
function toggleAdvancedFeatures() {
    DOM.advancedFeatures.classList.toggle('visible');
    document.querySelector('.toggle-btn').classList.toggle('active');

    if (DOM.advancedFeatures.classList.contains('visible')) {
        DOM.toggleText.textContent = '⚙️ HIDE ADVANCED FEATURES';
    } else {
        DOM.toggleText.textContent = '⚙️ SHOW ADVANCED FEATURES';
    }
}

async function apiCall(method, endpoint, data = null) {
    try {
        const options = {
            method: method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (data) options.body = JSON.stringify(data);

        const response = await fetch(API_BASE + endpoint, options);

        if (!response.ok) {
            let errorMessage = `Server error (${response.status})`;
            try {
                const result = await response.json();
                errorMessage = result.detail || errorMessage;
            } catch {
                errorMessage = `HTTP ${response.status}: ${response.statusText}`;
            }
            throw new Error(errorMessage);
        }

        const result = await response.json();
        return result;
    } catch (error) {
        throw error;
    }
}

function showStatus(message, type) {
    DOM.status.textContent = message;
    DOM.status.className = `status ${type}`;
}

function setButtonLoading(buttonElement, isLoading) {
    if (isLoading) {
        buttonElement.disabled = true;
        buttonElement.classList.add('loading');
        buttonElement.dataset.originalText = buttonElement.textContent;
    } else {
        buttonElement.disabled = false;
        buttonElement.classList.remove('loading');
        if (buttonElement.dataset.originalText) {
            buttonElement.textContent = buttonElement.dataset.originalText;
        }
    }
}

function clearValidationErrors(container) {
    const errors = container.querySelectorAll('.validation-error');
    errors.forEach(error => error.remove());
}

function showValidationError(container, message) {
    clearValidationErrors(container);
    const errorDiv = document.createElement('div');
    errorDiv.className = 'validation-error';
    errorDiv.textContent = message;
    container.appendChild(errorDiv);
}

// Output Target Management
let availableTargets = { targets: [], defaults: {}, active: {} };

async function loadOutputTargets() {
    try {
        availableTargets = await apiCall('GET', '/targets');
        updateTargetSelectors();
        updateTargetStatus();
    } catch (error) {
        console.error('Failed to load output targets:', error);
    }
}

async function refreshOutputTargets(e) {
    const refreshBtn = e ? e.target : document.querySelector('.refresh-targets-btn');

    try {
        setButtonLoading(refreshBtn, true);

        const result = await apiCall('POST', '/targets/refresh');
        showStatus(`Discovered ${result.chromecasts_found} Chromecast device(s)`, 'success');

        await loadOutputTargets();

    } catch (error) {
        showStatus(`Failed to refresh targets: ${error.message}`, 'error');
    } finally {
        setButtonLoading(refreshBtn, false);
    }
}

function getTargetIcon(targetType) {
    const icons = {
        'local-video': '📺',
        'local-audio': '🔊',
        'chromecast': '📡'
    };
    return icons[targetType] || '🎯';
}

function updateTargetSelectors() {
    const videoTargets = availableTargets.targets.filter(t =>
        t.capabilities.includes('video') && t.is_available
    );

    const audioTargets = availableTargets.targets.filter(t =>
        t.capabilities.includes('audio') && t.is_available
    );

    DOM.videoTargetSelect.innerHTML = '<option value="">Use Default (HDMI)</option>';
    videoTargets.forEach(target => {
        const option = document.createElement('option');
        option.value = target.id;
        const icon = getTargetIcon(target.type);
        option.textContent = `${icon} ${target.name}`;
        if (target.id === availableTargets.defaults.video) {
            option.textContent += ' (Default)';
        }
        DOM.videoTargetSelect.appendChild(option);
    });

    DOM.audioTargetSelect.innerHTML = '<option value="">Use Default (Audio Hat)</option>';
    audioTargets.forEach(target => {
        const option = document.createElement('option');
        option.value = target.id;
        const icon = getTargetIcon(target.type);
        option.textContent = `${icon} ${target.name}`;
        if (target.id === availableTargets.defaults.audio) {
            option.textContent += ' (Default)';
        }
        DOM.audioTargetSelect.appendChild(option);
    });
}

function updateTargetStatus() {
    if (availableTargets.active.video) {
        const target = availableTargets.targets.find(t => t.id === availableTargets.active.video);
        if (target) {
            DOM.videoTargetStatus.innerHTML = `<span style="text-shadow: 0 0 10px var(--neon-cyan);">● Active: ${target.name}</span>`;
        } else {
            DOM.videoTargetStatus.innerHTML = '';
        }
    } else {
        DOM.videoTargetStatus.innerHTML = '';
    }

    if (availableTargets.active.audio) {
        const target = availableTargets.targets.find(t => t.id === availableTargets.active.audio);
        if (target) {
            DOM.audioTargetStatus.innerHTML = `<span style="text-shadow: 0 0 10px var(--neon-cyan);">● Active: ${target.name}</span>`;
        } else {
            DOM.audioTargetStatus.innerHTML = '';
        }
    } else {
        DOM.audioTargetStatus.innerHTML = '';
    }
}

async function startStream() {
    const streamKey = DOM.streamKey.value;
    const sourceUrl = DOM.sourceUrl.value;
    const protocol = DOM.streamProtocol.value;

    if (!streamKey || !sourceUrl) {
        showStatus('Please fill in stream key and source URL', 'error');
        return;
    }

    const params = new URLSearchParams({ source_url: sourceUrl, protocol: protocol });
    await apiCall('POST', `/streams/${streamKey}/start?${params}`);
    refreshStatus();
}

async function startPlayback(e) {
    const startButton = e ? e.target : document.querySelector('#startPlaybackBtn');
    const playbackCard = startButton.closest('.card');

    clearValidationErrors(playbackCard);

    const streamKey = DOM.playbackKey.value.trim();
    const player = DOM.player.value;
    const mode = DOM.playMode.value;
    const protocol = DOM.playProtocol.value;

    if (!streamKey) {
        showValidationError(playbackCard, 'Please enter a stream key to play');
        return;
    }

    setButtonLoading(startButton, true);
    showStatus('Starting playback...', 'success');

    try {
        const params = new URLSearchParams({ player, mode, protocol });
        await apiCall('POST', `/playback/${streamKey}/start?${params}`);
        showStatus(`Successfully started playback of "${streamKey}" with ${player}`, 'success');
        refreshStatus();
    } catch (error) {
        showValidationError(playbackCard, `Failed to start playback: ${error.message}`);
        showStatus(`Playback failed: ${error.message}`, 'error');
    } finally {
        setButtonLoading(startButton, false);
    }
}

async function stopPlayback(e) {
    const stopButton = e ? e.target : document.querySelector('#stopPlaybackBtn');

    setButtonLoading(stopButton, true);
    showStatus('Stopping playback...', 'success');

    try {
        await apiCall('DELETE', '/playback/stop');
        showStatus('Playback stopped successfully', 'success');
        refreshStatus();
    } catch (error) {
        showStatus(`Failed to stop playback: ${error.message}`, 'error');
    } finally {
        setButtonLoading(stopButton, false);
    }
}

async function switchStream() {
    const newKey = DOM.switchKey.value;
    if (!newKey) {
        showStatus('Please enter a stream key', 'error');
        return;
    }
    await apiCall('POST', `/playback/switch/${newKey}`);
    refreshStatus();
}

async function switchPlayer(player) {
    await apiCall('POST', `/playback/player/${player}`);
    refreshStatus();
}

async function stopStream(streamKey) {
    await apiCall('DELETE', `/streams/${streamKey}`);
    refreshStatus();
}

async function displayImage() {
    const fileInput = DOM.imageFile;
    const duration = DOM.imageDuration.value || 10;

    if (!fileInput.files[0]) {
        showStatus('Please select an image file', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
        const response = await fetch(`/display/image?duration=${duration}`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to display image');
        }

        showStatus(result.message, 'success');
        refreshStatus();
    } catch (error) {
        showStatus(error.message, 'error');
    }
}

// Unified Video Playback Functions
function onVideoPresetChange() {
    if (DOM.videoPresets.value && DOM.videoPresets.value.startsWith('http')) {
        const selectedUrl = DOM.videoPresets.value;

        DOM.videoPresets.value = "";

        DOM.customVideoUrl.value = selectedUrl;
        playVideo();
    }
}

async function playVideo(e) {
    const playButton = e ? e.target : document.querySelector('#playVideoBtn');
    const videoCard = playButton ? playButton.closest('.card') : null;

    try {
        if (playButton) setButtonLoading(playButton, true);

        const videoUrl = DOM.customVideoUrl.value.trim();

        if (!videoUrl) {
            DOM.videoStatus.innerHTML = '<span style="color: #dc3545;">Please enter a valid URL</span>';
            return;
        }

        const urlRegex = /^https?:\/\/[^\s]+$/;
        if (!urlRegex.test(videoUrl)) {
            DOM.videoStatus.innerHTML = '<span style="color: #dc3545;">Please enter a valid URL starting with http:// or https://</span>';
            return;
        }

        let videoTitle = 'Custom Video';
        if (DOM.videoPresets.value === videoUrl) {
            videoTitle = DOM.videoPresets.options[DOM.videoPresets.selectedIndex].text;
        }

        const audioEnabled = DOM.videoAudioEnabled.checked;
        const duration = DOM.videoDuration.value;

        const selectedTarget = DOM.videoTargetSelect.value;

        DOM.videoStatus.innerHTML = `<span>Starting video playback...</span>`;

        const data = {
            youtube_url: videoUrl,
            mute: !audioEnabled
        };
        if (duration) data.duration = parseInt(duration);

        let endpoint = '/targets/play/video';
        if (selectedTarget) {
            endpoint += `?target=${encodeURIComponent(selectedTarget)}`;
        }

        await apiCall('POST', endpoint, data);

        const audioText = audioEnabled ? ' with audio' : ' (muted)';
        const targetName = selectedTarget ?
            availableTargets.targets.find(t => t.id === selectedTarget)?.name || 'selected target' :
            'default target';

        DOM.videoStatus.innerHTML = `<span style="text-shadow: 0 0 10px var(--neon-cyan);">📺 Playing: ${videoTitle}${audioText} on ${targetName}</span>`;
        showStatus('Video started successfully', 'success');

        await loadOutputTargets();
        refreshStatus();

    } catch (error) {
        DOM.videoStatus.innerHTML = `<span style="color: #dc3545;">Failed to start: ${error.message}</span>`;
        showStatus(`Video playback failed: ${error.message}`, 'error');
    } finally {
        if (playButton) setButtonLoading(playButton, false);
    }
}

async function stopVideo(e) {
    const stopButton = e ? e.target : document.querySelector('#stopVideoBtn');

    try {
        setButtonLoading(stopButton, true);
        DOM.videoStatus.innerHTML = '<span>Stopping video...</span>';

        await apiCall('DELETE', '/playback/stop');

        DOM.videoStatus.innerHTML = '<span style="color: rgba(255,255,255,0.5);">Video stopped</span>';
        showStatus('Video stopped', 'success');
        refreshStatus();

    } catch (error) {
        DOM.videoStatus.innerHTML = `<span style="color: #dc3545;">Failed to stop: ${error.message}</span>`;
        showStatus(`Failed to stop video: ${error.message}`, 'error');
    } finally {
        setButtonLoading(stopButton, false);
    }
}

async function displayQRCode(e) {
    const generateButton = e ? e.target : document.querySelector('#displayQRCodeBtn');
    const qrCard = generateButton.closest('.card');

    clearValidationErrors(qrCard);

    const content = DOM.qrContent.value.trim();
    const duration = DOM.qrDuration.value;

    if (!content) {
        showValidationError(qrCard, 'Please enter text or URL for the QR code');
        return;
    }

    setButtonLoading(generateButton, true);
    showStatus('Generating QR code...', 'success');

    try {
        const data = { content: content };
        if (duration) data.duration = parseInt(duration);

        await apiCall('POST', '/display/qrcode', data);
        showStatus(`QR code displayed successfully`, 'success');
        refreshStatus();
    } catch (error) {
        showValidationError(qrCard, `Failed to generate QR code: ${error.message}`);
        showStatus(`QR code generation failed: ${error.message}`, 'error');
    } finally {
        setButtonLoading(generateButton, false);
    }
}

// Audio streaming functions
async function startAudioStream(e) {
    const startButton = e ? e.target : document.querySelector('#startAudioBtn');
    const audioCard = startButton.closest('.card');

    clearValidationErrors(audioCard);

    const streamUrl = DOM.audioStreamUrl.value.trim();
    const volume = DOM.audioVolume.value;

    if (!streamUrl) {
        showValidationError(audioCard, 'Please enter an audio stream URL');
        return;
    }

    setButtonLoading(startButton, true);
    showStatus('Starting audio stream...', 'success');

    try {
        const selectedTarget = DOM.audioTargetSelect.value;

        const data = {
            stream_url: streamUrl,
            volume: parseInt(volume)
        };

        let endpoint = '/targets/play/audio';
        if (selectedTarget) {
            endpoint += `?target=${encodeURIComponent(selectedTarget)}`;
        }

        await apiCall('POST', endpoint, data);

        const targetName = selectedTarget ?
            availableTargets.targets.find(t => t.id === selectedTarget)?.name || 'selected target' :
            'default target';

        showStatus(`Audio stream started on ${targetName}`, 'success');

        await loadOutputTargets();
        updateAudioStatus();
    } catch (error) {
        showValidationError(audioCard, `Failed to start audio stream: ${error.message}`);
        showStatus(`Audio stream failed: ${error.message}`, 'error');
    } finally {
        setButtonLoading(startButton, false);
    }
}

async function stopAudioStream(e) {
    const stopButton = e ? e.target : document.querySelector('#stopAudioBtn');

    setButtonLoading(stopButton, true);
    showStatus('Stopping audio stream...', 'success');

    try {
        await apiCall('POST', '/audio/stop');
        showStatus('Audio stream stopped', 'success');
        updateAudioStatus();
    } catch (error) {
        showStatus(`Failed to stop audio stream: ${error.message}`, 'error');
    } finally {
        setButtonLoading(stopButton, false);
    }
}

function onQuickStreamChange() {
    const selectedUrl = DOM.quickStreamSelect.value;

    if (selectedUrl) {
        DOM.quickStreamSelect.value = '';

        DOM.audioStreamUrl.value = selectedUrl;

        DOM.audioStreamUrl.style.borderColor = '#28a745';

        setTimeout(() => {
            DOM.audioStreamUrl.style.borderColor = '';
        }, 2000);
    }
}

async function updateAudioStatus() {
    try {
        const status = await apiCall('GET', '/audio/status');

        if (status.is_playing) {
            const displayName = status.stream_name || status.current_stream || 'Unknown Stream';
            let statusHtml = `<span style="text-shadow: 0 0 10px var(--neon-cyan);">🎵 Playing: ${displayName}</span><br>
                             <span style="font-size: 12px;">Volume: ${status.volume}%</span>`;

            if (status.metadata) {
                const metadata = status.metadata;
                statusHtml += '<br><div style="margin-top: 8px; padding: 8px; background: rgba(0, 245, 255, 0.1); border-radius: 8px;">';
                statusHtml += `<div style="font-weight: bold;">${metadata.title}</div>`;
                if (metadata.artist) {
                    statusHtml += `<div style="font-size: 12px;">by ${metadata.artist}</div>`;
                }
                statusHtml += '</div>';
            }

            DOM.audioStatus.innerHTML = statusHtml;
        } else {
            DOM.audioStatus.innerHTML = '<span style="color: rgba(255,255,255,0.5);">No audio stream playing</span>';
        }
    } catch (error) {
        console.error('Failed to update audio status:', error);
    }
}

// Chromecast functions
async function discoverChromecasts(e) {
    const discoverButton = e ? e.target : document.querySelector('#discoverChromecastBtn');

    setButtonLoading(discoverButton, true);
    showStatus('Discovering Chromecast devices...', 'success');

    try {
        const result = await apiCall('GET', '/chromecast/discover');

        DOM.chromecastDevice.style.display = 'block';

        DOM.chromecastDevice.innerHTML = '<option value="">Select a device...</option>';

        if (result.devices && result.devices.length > 0) {
            result.devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device.name;
                option.textContent = `${device.name} (${device.model})`;
                DOM.chromecastDevice.appendChild(option);
            });

            showStatus(`Found ${result.count} Chromecast device(s)`, 'success');
        } else {
            showStatus('No Chromecast devices found on network', 'error');
        }
    } catch (error) {
        showStatus(`Failed to discover Chromecast devices: ${error.message}`, 'error');
    } finally {
        setButtonLoading(discoverButton, false);
    }
}

async function startChromecast(e) {
    const startButton = e ? e.target : document.querySelector('#startChromecastBtn');
    const chromecastCard = startButton.closest('.card');

    clearValidationErrors(chromecastCard);

    const mediaUrl = DOM.chromecastUrl.value.trim();
    const deviceName = DOM.chromecastDevice.value;

    if (!mediaUrl) {
        showValidationError(chromecastCard, 'Please enter a media URL to cast');
        return;
    }

    setButtonLoading(startButton, true);
    showStatus('Starting Chromecast...', 'success');

    try {
        const data = {
            media_url: mediaUrl
        };

        if (deviceName) {
            data.device_name = deviceName;
        }

        const result = await apiCall('POST', '/chromecast/start', data);
        showStatus(`Started casting to Chromecast (${result.media_type})`, 'success');
        updateChromecastStatus();
    } catch (error) {
        showValidationError(chromecastCard, `Failed to start casting: ${error.message}`);
        showStatus(`Chromecast failed: ${error.message}`, 'error');
    } finally {
        setButtonLoading(startButton, false);
    }
}

async function pauseChromecast(e) {
    const pauseButton = e ? e.target : document.querySelector('#pauseChromecastBtn');

    setButtonLoading(pauseButton, true);

    try {
        await apiCall('POST', '/chromecast/pause');
        showStatus('Chromecast paused', 'success');
        updateChromecastStatus();
    } catch (error) {
        showStatus(`Failed to pause Chromecast: ${error.message}`, 'error');
    } finally {
        setButtonLoading(pauseButton, false);
    }
}

async function stopChromecast(e) {
    const stopButton = e ? e.target : document.querySelector('#stopChromecastBtn');

    setButtonLoading(stopButton, true);
    showStatus('Stopping Chromecast...', 'success');

    try {
        await apiCall('POST', '/chromecast/stop');
        showStatus('Chromecast stopped', 'success');
        updateChromecastStatus();
    } catch (error) {
        showStatus(`Failed to stop Chromecast: ${error.message}`, 'error');
    } finally {
        setButtonLoading(stopButton, false);
    }
}

function updateChromecastVolumeDisplay() {
    const volume = DOM.chromecastVolume.value;
    DOM.chromecastVolumeDisplay.textContent = volume;

    if (DOM.chromecastStatus.innerHTML.includes('Casting')) {
        setChromecastVolume();
    }
}

async function setChromecastVolume() {
    const volume = DOM.chromecastVolume.value;

    try {
        await apiCall('PUT', '/chromecast/volume', {
            volume: parseFloat(volume) / 100
        });
    } catch (error) {
        console.error('Failed to set Chromecast volume:', error);
    }
}

async function updateChromecastStatus() {
    try {
        const status = await apiCall('GET', '/chromecast/status');

        if (status.is_casting) {
            let statusHtml = `<span style="text-shadow: 0 0 10px var(--neon-cyan);">📺 Casting to: ${status.device_name}</span><br>`;
            statusHtml += `<span style="font-size: 12px;">Type: ${status.media_type}</span><br>`;

            if (status.player_state) {
                statusHtml += `<span style="font-size: 12px;">State: ${status.player_state}</span><br>`;
            }

            if (status.duration && status.current_time !== undefined) {
                const currentMin = Math.floor(status.current_time / 60);
                const currentSec = Math.floor(status.current_time % 60);
                const durationMin = Math.floor(status.duration / 60);
                const durationSec = Math.floor(status.duration % 60);
                statusHtml += `<span style="font-size: 12px;">Time: ${currentMin}:${currentSec.toString().padStart(2, '0')} / ${durationMin}:${durationSec.toString().padStart(2, '0')}</span>`;
            }

            DOM.chromecastStatus.innerHTML = statusHtml;
        } else {
            DOM.chromecastStatus.innerHTML = '<span style="color: rgba(255,255,255,0.5);">Not casting</span>';
            if (status.available_devices > 0) {
                DOM.chromecastStatus.innerHTML += `<br><span style="font-size: 12px;">${status.available_devices} device(s) available</span>`;
            }
        }
    } catch (error) {
        console.error('Failed to update Chromecast status:', error);
    }
}

// Cast Receiver status update
async function updateCastReceiverStatus() {
    try {
        const status = await apiCall('GET', '/cast-receiver/status');

        if (status.is_running) {
            let statusHtml = `<span style="text-shadow: 0 0 10px var(--neon-cyan);">✅ Receiver Active</span><br>`;
            statusHtml += `<span style="font-size: 12px;">Device Name: ${status.device_name}</span><br>`;
            statusHtml += `<span style="font-size: 12px;">IP: ${status.local_ip}:${status.dial_port}</span>`;

            if (status.has_session && status.session) {
                statusHtml += '<br><br><div style="border-top: 1px solid rgba(0,245,255,0.3); padding-top: 10px; margin-top: 10px;">';
                statusHtml += `<span style="text-shadow: 0 0 10px var(--neon-cyan);">📺 Currently Playing:</span><br>`;
                statusHtml += `<span style="font-size: 12px;">${status.session.title || 'Media'}</span><br>`;
                statusHtml += `<span style="font-size: 12px;">Type: ${status.session.media_type}</span>`;
                statusHtml += '</div>';
            }

            DOM.castReceiverStatus.innerHTML = statusHtml;
        } else {
            DOM.castReceiverStatus.innerHTML = '<span style="color: rgba(255,0,110,0.8);">❌ Receiver Inactive</span>';
        }
    } catch (error) {
        console.error('Failed to update cast receiver status:', error);
        DOM.castReceiverStatus.innerHTML = '<span style="color: rgba(255,0,110,0.8);">❌ Status check failed</span>';
    }
}


// Background management
async function setBackground() {
    if (!DOM.backgroundFile.files[0]) {
        showStatus('Please select a background image', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', DOM.backgroundFile.files[0]);

    try {
        const response = await fetch('/background/set', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to set background');
        }

        showStatus(result.message, 'success');
        refreshStatus();
    } catch (error) {
        showStatus(error.message, 'error');
    }
}

async function showBackground() {
    await apiCall('POST', '/background/show');
    refreshStatus();
}

async function setBackgroundMode(mode) {
    DOM.staticModeBtn.disabled = true;

    try {
        showStatus(`Setting background mode to ${mode}...`, 'success');

        const response = await fetch('/background/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: mode })
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to set background mode');
        }

        showStatus(`Background mode set to ${mode}`, 'success');
        await refreshBackgroundStatus();

    } catch (error) {
        showStatus(`Failed to set background mode: ${error.message}`, 'error');
    } finally {
        DOM.staticModeBtn.disabled = false;
    }
}

async function refreshBackgroundStatus() {
    try {
        const response = await fetch('/background/mode');
        const status = await response.json();

        let statusText = `Mode: ${status.mode}`;
        if (!status.is_running) {
            statusText += ' (not running)';
        }
        DOM.backgroundStatus.textContent = statusText;

    } catch (error) {
        console.error('Failed to refresh background status:', error);
        DOM.backgroundStatus.textContent = 'Error loading status';
    }
}

async function refreshBackground() {
    try {
        showStatus('Refreshing background...', 'success');

        const response = await fetch('/background/refresh', {
            method: 'POST'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to refresh');
        }

        showStatus(result.message || 'Background refreshed', 'success');
        await refreshBackgroundStatus();

    } catch (error) {
        showStatus(`Failed to refresh: ${error.message}`, 'error');
    }
}

async function toggleScreenStream() {
    const streamCard = DOM.screenStreamButton.closest('.card');

    clearValidationErrors(streamCard);

    try {
        const status = await fetch('/screen-stream/status').then(r => r.json());

        if (status.active) {
            setButtonLoading(DOM.screenStreamButton, true);
            DOM.screenStreamStatus.textContent = 'Stopping screen stream...';

            await apiCall('DELETE', '/screen-stream/stop');
            DOM.screenStreamButton.textContent = 'START SCREEN STREAM';
            DOM.screenStreamButton.className = '';
            DOM.screenStreamStatus.textContent = '';
            showStatus('Screen streaming stopped', 'success');
        } else {
            const streamKey = DOM.screenStreamKey.value.trim();
            const protocol = DOM.screenStreamProtocol.value;

            if (!streamKey) {
                showValidationError(streamCard, 'Please enter a stream key');
                return;
            }

            setButtonLoading(DOM.screenStreamButton, true);
            DOM.screenStreamStatus.textContent = 'Starting screen stream...';

            await apiCall('POST', `/screen-stream/${streamKey}/start?protocol=${protocol}`);
            DOM.screenStreamButton.textContent = 'STOP SCREEN STREAM';
            DOM.screenStreamButton.className = 'danger';
            DOM.screenStreamStatus.innerHTML = `<span style="color: var(--neon-cyan);">🔴 Streaming "${streamKey}"</span>`;
            showStatus(`Screen streaming started: ${streamKey}`, 'success');
        }

        refreshStatus();
    } catch (error) {
        showValidationError(streamCard, `Screen streaming error: ${error.message}`);
        showStatus(`Screen streaming failed: ${error.message}`, 'error');
        DOM.screenStreamStatus.textContent = '';
    } finally {
        setButtonLoading(DOM.screenStreamButton, false);
    }
}

async function updateScreenStreamUI() {
    try {
        const status = await fetch('/screen-stream/status').then(r => r.json());

        if (status.active) {
            DOM.screenStreamButton.textContent = 'STOP SCREEN STREAM';
            DOM.screenStreamButton.className = 'danger';
            DOM.screenStreamStatus.innerHTML = `<span style="color: var(--neon-cyan);">🔴 Streaming "${status.stream_key}"</span>`;
        } else {
            DOM.screenStreamButton.textContent = 'START SCREEN STREAM';
            DOM.screenStreamButton.className = '';
            DOM.screenStreamStatus.textContent = '';
        }
    } catch (error) {
        console.error('Failed to update screen stream UI:', error);
    }
}

async function refreshStatus() {
    try {
        const [status, streams] = await Promise.all([
            fetch('/status').then(r => r.json()),
            fetch('/streams').then(r => r.json())
        ]);

        const stats = status.system_stats;
        DOM.systemStats.innerHTML = `
            <div class="stat-item">
                <strong>CPU</strong><br>${stats.cpu_percent?.toFixed(1) || 'N/A'}%
            </div>
            <div class="stat-item">
                <strong>Memory</strong><br>${stats.memory_percent?.toFixed(1) || 'N/A'}%
            </div>
            <div class="stat-item">
                <strong>Temperature</strong><br>${stats.temperature?.toFixed(1) || 'N/A'}°C
            </div>
            <div class="stat-item">
                <strong>Active Streams</strong><br>${status.active_streams}
            </div>
        `;

        if (Object.keys(streams.active_streams).length === 0) {
            DOM.activeStreams.innerHTML = 'No active streams';
        } else {
            DOM.activeStreams.innerHTML = Object.entries(streams.active_streams)
                .map(([key, info]) => `
                    <div class="stream-item">
                        <div>
                            <strong>${key}</strong><br>
                            <small>${info.source_url}</small><br>
                            <small>Started: ${new Date(info.started_at).toLocaleTimeString()}</small>
                        </div>
                        <button onclick="stopStream('${key}')" class="danger small-btn">STOP</button>
                    </div>
                `).join('');
        }

        const playback = streams.current_playback;

        if (playback.stream) {
            let playbackHtml = `
                <strong>Stream:</strong> ${playback.stream}<br>
                <strong>Player:</strong> ${playback.player}<br>
                <strong>Protocol:</strong> ${playback.protocol}
            `;

            if (playback.stats) {
                const s = playback.stats;
                const dropPercent = s.drop_percentage ? s.drop_percentage.toFixed(2) : '0.00';
                const fpsDisplay = s.fps_current ? s.fps_current.toFixed(1) : 'N/A';

                playbackHtml += `<br><br><strong>Performance:</strong><br>
                <strong>FPS:</strong> ${fpsDisplay}<br>
                <strong>Frames:</strong> ${s.total_frames || 0}<br>
                <strong>Dropped:</strong> ${s.dropped_frames || 0} (${dropPercent}%)`;
            }

            DOM.currentPlayback.innerHTML = playbackHtml;
        } else {
            try {
                const audioStatus = await fetch('/audio/status').then(r => r.json());
                if (audioStatus.is_playing) {
                    let audioInfo = `<strong>🎵 Audio:</strong> ${audioStatus.stream_name || 'Audio Stream'}<br>
                                   <strong>Volume:</strong> ${audioStatus.volume}%`;

                    if (audioStatus.metadata) {
                        const meta = audioStatus.metadata;
                        audioInfo += `<br><strong>Now Playing:</strong> ${meta.title}`;
                        if (meta.artist) audioInfo += ` by ${meta.artist}`;
                    }

                    DOM.currentPlayback.innerHTML = audioInfo;
                } else {
                    DOM.currentPlayback.innerHTML = 'No active playback';
                }
            } catch (error) {
                DOM.currentPlayback.innerHTML = 'No active playback';
            }
        }

        showStatus('Status refreshed', 'success');
        updateAudioStatus();
        updateChromecastStatus();
        updateCastReceiverStatus();

    } catch (error) {
        showStatus('Failed to refresh status', 'error');
    }
}

async function loadResolution() {
    try {
        const response = await fetch('/resolution');
        const resolution = await response.json();

        DOM.resolutionDisplay.textContent = resolution.resolution_string.toUpperCase();
    } catch (error) {
        DOM.resolutionDisplay.textContent = 'RESOLUTION DETECTION FAILED';
    }
}

// TV Control Functions
async function powerOnTV() {
    try {
        setButtonLoading(DOM.tvPowerOnBtn, true);
        showStatus('Powering on TV...', 'success');

        const response = await fetch('/cec/tv/power-on', { method: 'POST' });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to power on TV');
        }

        showStatus(result.message, 'success');
        setTimeout(() => refreshCECStatus(), 2000);

    } catch (error) {
        showStatus(`Failed to power on TV: ${error.message}`, 'error');
    } finally {
        setButtonLoading(DOM.tvPowerOnBtn, false);
    }
}

async function powerOffTV() {
    try {
        setButtonLoading(DOM.tvPowerOffBtn, true);
        showStatus('Powering off TV...', 'success');

        const response = await fetch('/cec/tv/power-off', { method: 'POST' });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to power off TV');
        }

        showStatus(result.message, 'success');
        setTimeout(() => refreshCECStatus(), 2000);

    } catch (error) {
        showStatus(`Failed to power off TV: ${error.message}`, 'error');
    } finally {
        setButtonLoading(DOM.tvPowerOffBtn, false);
    }
}

async function refreshCECStatus() {
    try {
        const response = await fetch('/cec/status');
        const status = await response.json();

        if (status.available) {
            DOM.cecAvailability.textContent = '✅ Available';
            DOM.cecAvailability.style.color = 'var(--neon-cyan)';

            DOM.tvAddress.textContent = status.tv_address || '-';

            if (status.tv_power && status.tv_power.success) {
                const powerState = status.tv_power.power_status;
                if (powerState === 'on') {
                    DOM.tvPowerStatus.textContent = '🟢 On';
                    DOM.tvPowerStatus.style.color = 'var(--neon-cyan)';
                } else if (powerState === 'standby') {
                    DOM.tvPowerStatus.textContent = '🔴 Standby';
                    DOM.tvPowerStatus.style.color = '#dc3545';
                } else {
                    DOM.tvPowerStatus.textContent = '❓ Unknown';
                }
            } else {
                DOM.tvPowerStatus.textContent = '❓ Check Failed';
            }

            DOM.tvPowerOnBtn.disabled = false;
            DOM.tvPowerOffBtn.disabled = false;

        } else {
            DOM.cecAvailability.textContent = '❌ Not Available';
            DOM.cecAvailability.style.color = '#dc3545';
            DOM.tvPowerStatus.textContent = '❌ Unavailable';
            DOM.tvAddress.textContent = '-';

            DOM.tvPowerOnBtn.disabled = true;
            DOM.tvPowerOffBtn.disabled = true;
        }

    } catch (error) {
        console.error('Failed to refresh CEC status:', error);
    }
}

// Webcast Functions
async function startWebcast() {
    try {
        setButtonLoading(DOM.webcastStartBtn, true);

        const url = DOM.webcastUrl.value;
        if (!url) {
            throw new Error('Please enter a website URL');
        }

        const viewportSize = DOM.viewportSize.value;
        const [width, height] = viewportSize.split('x').map(Number);

        const config = {
            url: url,
            viewport_width: width,
            viewport_height: height,
            scroll_delay: parseFloat(DOM.scrollDelay.value),
            scroll_percentage: parseFloat(DOM.scrollPercentage.value),
            overlap_percentage: parseFloat(DOM.overlapPercentage.value),
            loop_count: parseInt(DOM.loopCount.value),
            zoom_level: 1.0
        };

        showStatus('Starting webcast...', 'success');

        const response = await fetch('/webcast/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to start webcast');
        }

        showStatus('Webcast started successfully', 'success');
        updateWebcastUI(result);

    } catch (error) {
        showStatus(`Failed to start webcast: ${error.message}`, 'error');
    } finally {
        setButtonLoading(DOM.webcastStartBtn, false);
    }
}

async function stopWebcast() {
    try {
        setButtonLoading(DOM.webcastStopBtn, true);
        showStatus('Stopping webcast...', 'success');

        const response = await fetch('/webcast/stop', { method: 'POST' });
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || 'Failed to stop webcast');
        }

        showStatus('Webcast stopped', 'success');
        updateWebcastUI(result);

    } catch (error) {
        showStatus(`Failed to stop webcast: ${error.message}`, 'error');
    } finally {
        setButtonLoading(DOM.webcastStopBtn, false);
    }
}

function updateWebcastUI(status) {
    if (status.status === 'running') {
        DOM.webcastState.textContent = '🟢 Running';
        DOM.webcastState.style.color = 'var(--neon-cyan)';
        DOM.webcastStartBtn.disabled = true;
        DOM.webcastStopBtn.disabled = false;
    } else {
        DOM.webcastState.textContent = '🔴 Stopped';
        DOM.webcastState.style.color = '#dc3545';
        DOM.webcastStartBtn.disabled = false;
        DOM.webcastStopBtn.disabled = true;
    }
}

// Spotify Functions
async function refreshSpotifyStatus() {
    try {
        const serviceResponse = await fetch('/audio/spotify/status');
        const serviceStatus = await serviceResponse.json();

        if (serviceStatus.service_running) {
            DOM.spotifyServiceStatus.textContent = '✅ Active - Ready to cast';
            DOM.spotifyServiceStatus.style.color = 'var(--neon-cyan)';
        } else {
            DOM.spotifyServiceStatus.textContent = '❌ Service not running';
            DOM.spotifyServiceStatus.style.color = '#dc3545';
        }

        const playbackResponse = await fetch('/audio/spotify/playback');
        const playbackStatus = await playbackResponse.json();

        if (playbackStatus.is_playing) {
            DOM.spotifyPlaybackInfo.style.display = 'block';

            let trackDisplay = playbackStatus.current_track_id || '-';
            if (trackDisplay.startsWith('spotify:track:')) {
                const trackId = trackDisplay.split(':')[2];
                trackDisplay = `Track ${trackId.substring(0, 8)}...`;

                if (playbackStatus.track_info && playbackStatus.track_info.spotify_url) {
                    DOM.spotifyTrackId.innerHTML =
                        `<a href="${playbackStatus.track_info.spotify_url}" target="_blank" style="color: #1DB954;">${trackDisplay}</a>`;
                } else {
                    DOM.spotifyTrackId.textContent = trackDisplay;
                }
            } else {
                DOM.spotifyTrackId.textContent = trackDisplay;
            }

            if (playbackStatus.track_info && playbackStatus.track_info.duration_ms) {
                const minutes = Math.floor(playbackStatus.track_info.duration_ms / 60000);
                const seconds = Math.floor((playbackStatus.track_info.duration_ms % 60000) / 1000);
                DOM.spotifyDuration.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
            } else {
                DOM.spotifyDuration.textContent = '-';
            }

            if (playbackStatus.last_event_time) {
                const eventTime = new Date(playbackStatus.last_event_time);
                DOM.spotifyLastEvent.textContent =
                    `Last update: ${eventTime.toLocaleTimeString()}`;
            } else {
                DOM.spotifyLastEvent.textContent = '-';
            }

            DOM.spotifyServiceStatus.textContent = '🎵 Playing on Spotify';
            DOM.spotifyServiceStatus.style.color = '#1DB954';
        } else if (playbackStatus.is_session_connected) {
            DOM.spotifyPlaybackInfo.style.display = 'none';
            DOM.spotifyServiceStatus.textContent = '✅ Connected - Not playing';
            DOM.spotifyServiceStatus.style.color = 'var(--neon-cyan)';
        } else {
            DOM.spotifyPlaybackInfo.style.display = 'none';
        }

    } catch (error) {
        console.error('Failed to refresh Spotify status:', error);
        DOM.spotifyServiceStatus.textContent = '❌ Error checking status';
        DOM.spotifyPlaybackInfo.style.display = 'none';
    }
}

// Load media sources
async function loadMediaSources() {
    try {
        const mediaSources = await apiCall('GET', '/media-sources');

        if (DOM.quickStreamSelect && mediaSources.music_streams) {
            while (DOM.quickStreamSelect.children.length > 1) {
                DOM.quickStreamSelect.removeChild(DOM.quickStreamSelect.lastChild);
            }

            if (mediaSources.music_streams.somafm) {
                const somaGroup = document.createElement('optgroup');
                somaGroup.label = 'soma.fm Stations';
                mediaSources.music_streams.somafm.forEach(station => {
                    const option = document.createElement('option');
                    option.value = station.url;
                    option.textContent = station.name;
                    somaGroup.appendChild(option);
                });
                DOM.quickStreamSelect.appendChild(somaGroup);
            }

            if (mediaSources.music_streams.bbc) {
                const bbcGroup = document.createElement('optgroup');
                bbcGroup.label = 'BBC Radio';
                mediaSources.music_streams.bbc.forEach(station => {
                    const option = document.createElement('option');
                    option.value = station.url;
                    option.textContent = station.name;
                    bbcGroup.appendChild(option);
                });
                DOM.quickStreamSelect.appendChild(bbcGroup);
            }
        }

        if (DOM.videoPresets && mediaSources.youtube_channels) {
            const staticOptions = Array.from(DOM.videoPresets.options).slice(0, 2);
            const customOption = DOM.videoPresets.querySelector('option[value="custom"]');

            DOM.videoPresets.innerHTML = '';
            staticOptions.forEach(opt => DOM.videoPresets.appendChild(opt));

            Object.entries(mediaSources.youtube_channels).forEach(([category, videos]) => {
                const group = document.createElement('optgroup');
                group.label = category.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

                videos.forEach(video => {
                    const option = document.createElement('option');
                    option.value = video.url;
                    option.textContent = video.name;
                    group.appendChild(option);
                });
                DOM.videoPresets.appendChild(group);
            });

            if (customOption) {
                const customGroup = document.createElement('optgroup');
                customGroup.label = 'Custom';
                customGroup.appendChild(customOption.cloneNode(true));
                DOM.videoPresets.appendChild(customGroup);
            }
        }
    } catch (error) {
        console.error('Failed to load media sources:', error);
    }
}

// Initialize on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
    cacheDOMElements();
    loadMediaSources();

    // Bind event listeners for primary controls
    DOM.playVideoBtn.addEventListener('click', playVideo);
    DOM.stopVideoBtn.addEventListener('click', stopVideo);
    DOM.startAudioBtn.addEventListener('click', startAudioStream);
    DOM.stopAudioBtn.addEventListener('click', stopAudioStream);
    DOM.discoverChromecastBtn.addEventListener('click', discoverChromecasts);
    DOM.startChromecastBtn.addEventListener('click', startChromecast);
    DOM.pauseChromecastBtn.addEventListener('click', pauseChromecast);
    DOM.stopChromecastBtn.addEventListener('click', stopChromecast);
    DOM.startPlaybackBtn.addEventListener('click', startPlayback);
    DOM.stopPlaybackBtn.addEventListener('click', stopPlayback);
    DOM.startStreamBtn.addEventListener('click', startStream);
    DOM.displayImageBtn.addEventListener('click', displayImage);
    DOM.stopDisplayImageBtn.addEventListener('click', stopPlayback);
    DOM.displayQRCodeBtn.addEventListener('click', displayQRCode);
    DOM.stopQRCodeBtn.addEventListener('click', stopPlayback);
    DOM.setBackgroundBtn.addEventListener('click', setBackground);
    DOM.refreshBackgroundBtn.addEventListener('click', refreshBackground);
    DOM.showBackgroundBtn.addEventListener('click', showBackground);
    DOM.refreshStatusBtn.addEventListener('click', refreshStatus);
    DOM.switchStreamBtn.addEventListener('click', switchStream);
    DOM.switchPlayerMpvBtn.addEventListener('click', () => switchPlayer('mpv'));
    DOM.switchPlayerFfplayBtn.addEventListener('click', () => switchPlayer('ffplay'));
    DOM.toggleAdvancedBtn.addEventListener('click', toggleAdvancedFeatures);
    DOM.refreshSpotifyBtn.addEventListener('click', refreshSpotifyStatus);
    DOM.refreshCECBtn.addEventListener('click', refreshCECStatus);
    DOM.screenStreamButton.addEventListener('click', toggleScreenStream);
    DOM.staticModeBtn.addEventListener('click', () => setBackgroundMode('static'));
    DOM.tvPowerOnBtn.addEventListener('click', powerOnTV);
    DOM.tvPowerOffBtn.addEventListener('click', powerOffTV);
    DOM.webcastStartBtn.addEventListener('click', startWebcast);
    DOM.webcastStopBtn.addEventListener('click', stopWebcast);

    // Tab buttons
    document.getElementById('tab-btn-streams').addEventListener('click', () => switchTab('streams'));
    document.getElementById('tab-btn-display').addEventListener('click', () => switchTab('display'));
    document.getElementById('tab-btn-system').addEventListener('click', () => switchTab('system'));
    document.getElementById('tab-btn-advanced').addEventListener('click', () => switchTab('advanced'));

    // Refresh targets buttons (class-based, multiple instances)
    document.querySelectorAll('.refresh-targets-btn').forEach(btn => {
        btn.addEventListener('click', refreshOutputTargets);
    });

    // Select/input change handlers
    DOM.videoPresets.addEventListener('change', onVideoPresetChange);
    DOM.quickStreamSelect.addEventListener('change', onQuickStreamChange);
    DOM.chromecastVolume.addEventListener('change', updateChromecastVolumeDisplay);
    DOM.chromecastVolume.addEventListener('input', updateChromecastVolumeDisplay);

    if (DOM.audioVolume && DOM.volumeDisplay) {
        DOM.audioVolume.addEventListener('input', function() {
            DOM.volumeDisplay.textContent = this.value;
        });

        DOM.audioVolume.addEventListener('change', async function() {
            try {
                await apiCall('PUT', '/audio/volume', { volume: parseInt(this.value) });
            } catch (error) {
                console.error('Failed to set volume:', error);
            }
        });
    }

    // Auto-refresh intervals
    setInterval(refreshStatus, POLL_INTERVALS.STATUS);
    setInterval(updateScreenStreamUI, POLL_INTERVALS.SCREEN_STREAM);
    setInterval(refreshBackgroundStatus, POLL_INTERVALS.BACKGROUND);
    setInterval(refreshCECStatus, POLL_INTERVALS.CEC);
    setInterval(refreshSpotifyStatus, POLL_INTERVALS.SPOTIFY);
    setInterval(loadOutputTargets, POLL_INTERVALS.OUTPUT_TARGETS);

    // Initial load
    loadResolution();
    loadOutputTargets();
    refreshStatus();
    updateScreenStreamUI();
    refreshBackgroundStatus();
    refreshCECStatus();
    refreshSpotifyStatus();
});
