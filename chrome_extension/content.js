
let savedDistractionTime = null;
let replay = null;
let lastEventId = -1;
let polling = false;
let connected = false;
let videoId = new URL(location.href).searchParams.get("v");
let capture = null;
let bridgeSession = null;
const pendingIntervals = new Map();

function saveInterval(interval) {
    pendingIntervals.set(interval.id, interval);
    chrome.runtime.sendMessage({type: "saveInterval", interval}, response => {
        if (chrome.runtime.lastError || !response?.ok) {
            showStatus("Interval save failed; retrying while this tab stays open");
        } else {
            pendingIntervals.delete(interval.id);
            showStatus("Interval saved. Use Explain What I Missed in NeuroLearn.");
        }
    });
}
setInterval(() => {
    for (const interval of pendingIntervals.values()) saveInterval(interval);
}, 5000);

function resetVideo() {
    const currentId = new URL(location.href).searchParams.get("v");
    if (currentId === videoId) return;
    if (replay) replay.video.playbackRate = replay.originalSpeed;
    videoId = currentId;
    savedDistractionTime = null;
    capture = null;
    replay = null;
}

// Find the YouTube video
function getVideo() {
    return document.querySelector("video.html5-main-video")
        || document.querySelector("video");
}

// Show status in the top-right corner of YouTube
function showStatus(message) {
    let label = document.getElementById("neurotech-bridge-status");

    if (!label) {
        label = document.createElement("div");
        label.id = "neurotech-bridge-status";
        label.style.cssText =
            "position:fixed;right:15px;top:75px;z-index:999999;" +
            "background:#222;color:white;padding:9px 12px;border-radius:8px;" +
            "font:13px Arial,sans-serif;pointer-events:none";
        document.body.appendChild(label);
    }

    label.textContent = "Neurotech: " + message;
}

// Process commands from the desktop app
function handleCommand(action) {
    resetVideo();
    const video = getVideo();

    if (!video) {
        showStatus("YouTube video not found");
        return;
    }

    if (action === "distracted") {
        if (!videoId || video.paused || video.ended || replay) return;
        capture = {id: crypto.randomUUID(), video_id: videoId, start: video.currentTime};
        savedDistractionTime = video.currentTime;
        showStatus(`Distraction saved at ${savedDistractionTime.toFixed(1)}s`);

    } else if (action === "focused") {
        if (capture) {
            const interval = {...capture, end: video.currentTime};
            capture = null;
            if (interval.end > interval.start && interval.end - interval.start <= 1800) {
                saveInterval(interval);
            } else {
                showStatus("Interval invalid after seek, pause, or more than 30 minutes");
            }
        }
        // Keep the saved timestamp
        if (savedDistractionTime !== null) {
            showStatus(
                `Focus returned. Saved ${savedDistractionTime.toFixed(1)}s`
            );
        }

    } else if (action === "discard") {
        capture = null;
        savedDistractionTime = null;
        showStatus("Distraction cleared");

    } else if (action === "rewind") {
        if (savedDistractionTime === null) {
            showStatus("No distraction timestamp saved");
            return;
        }

        // Remember where the student was before rewinding
        const catchUpTime = video.currentTime;

        if (catchUpTime <= savedDistractionTime) {
            showStatus("Video has not moved past distraction");
            return;
        }

        // Read the actual playback speed
        const originalSpeed = video.playbackRate;

        // Slow down by 0.25x
        const slowerSpeed = Math.max(
            0.1,
            Math.round((originalSpeed - 0.25) * 100) / 100
        );

        replay = {
            video,
            catchUpTime,
            originalSpeed
        };

        // Rewind to the first distraction
        video.currentTime = savedDistractionTime;
        video.playbackRate = slowerSpeed;
        video.play().catch(() => {});

        showStatus(
            `Replaying at ${slowerSpeed}x, then ${originalSpeed}x`
        );

        savedDistractionTime = null;
    }
}

// Check whether the video has caught up
setInterval(() => {
    resetVideo();

    if (!replay) return;

    const video = getVideo();

    if (video !== replay.video) {
        replay.video.playbackRate = replay.originalSpeed;
        replay = null;
        showStatus("Video changed; replay stopped");
        return;
    }

    if (video.currentTime >= replay.catchUpTime - 0.05 || video.ended) {
        video.playbackRate = replay.originalSpeed;

        showStatus(
            `Caught up! Restored ${replay.originalSpeed}x`
        );

        replay = null;
    }
}, 100);

// Receive commands from Python
function poll() {
    if (polling) return;

    polling = true;

    chrome.runtime.sendMessage({
        type: "poll",
        after: lastEventId
    }, (response) => {
        polling = false;

        if (chrome.runtime.lastError || !response || !response.ok) {
            if (connected) {
                showStatus("Desktop app disconnected");
            }
            connected = false;
            lastEventId = -1;
            capture = null;
            savedDistractionTime = null;
            return;
        }

        if (!connected) {
            showStatus("Connected to desktop app");
        }

        connected = true;
        if (bridgeSession !== null && bridgeSession !== response.data.session) {
            capture = null;
            savedDistractionTime = null;
            lastEventId = -1;
            bridgeSession = response.data.session;
            return;
        }
        bridgeSession = response.data.session;
        lastEventId = response.data.last_id;

        for (const event of response.data.events) {
            handleCommand(event.action);
        }
    });
}

poll();
setInterval(poll, 250);
