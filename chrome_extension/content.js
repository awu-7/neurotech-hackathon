
let savedDistractionTime = null;
let replay = null;
let lastEventId = -1;
let polling = false;
let connected = false;
let videoId = new URL(location.href).searchParams.get("v");

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


function closeRewindPrompt() {
    const oldPrompt = document.getElementById("neurotech-rewind-prompt");

    if (oldPrompt) {
        oldPrompt.remove();
    }
}

function showRewindPrompt() {
    if (savedDistractionTime === null || !getVideo()) {
        showStatus("No distraction timestamp saved");
        return;
    }

    closeRewindPrompt();

    const prompt = document.createElement("div");
    prompt.id = "neurotech-rewind-prompt";

    prompt.style.cssText = `
        position: fixed;
        top: 100px;
        right: 20px;
        width: 320px;
        box-sizing: border-box;
        z-index: 2147483647;
        background: #141923;
        color: white;
        padding: 20px;
        border: 1px solid #3e5d81;
        border-radius: 14px;
        box-shadow: 0 10px 35px rgba(0,0,0,0.5);
        font-family: Arial, sans-serif;
        pointer-events: auto;
    `;

    prompt.innerHTML = `
        <div style="
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
        ">
            Focus returned!
        </div>

        <div style="
            font-size: 14px;
            line-height: 1.5;
            margin-bottom: 18px;
            color: #cbd5e1;
        ">
            You may have missed part of the lecture.
            Would you like to rewind to when you lost focus?
        </div>

        <div style="display: flex; gap: 10px;">
            <button id="neurotech-rewind-button" style="
                background: #377cf6;
                color: white;
                border: none;
                padding: 11px 12px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: bold;
                flex: 1;
            ">
                Rewind Lecture
            </button>

            <button id="neurotech-continue-button" style="
                background: #374151;
                color: white;
                border: none;
                padding: 11px 12px;
                border-radius: 8px;
                cursor: pointer;
                font-weight: bold;
                flex: 1;
            ">
                Continue
            </button>
        </div>
    `;

    // Prevent clicks on the popup from affecting YouTube.
    prompt.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
    });

    prompt.addEventListener("click", (event) => {
        event.stopPropagation();
    });

    prompt.querySelector("#neurotech-rewind-button")
        .addEventListener("click", () => {
            closeRewindPrompt();
            handleCommand("rewind");
        });

    prompt.querySelector("#neurotech-continue-button")
        .addEventListener("click", () => {
            closeRewindPrompt();
            handleCommand("discard");
        });

    // Keep the popup over the video, even in fullscreen.
    const parent = document.fullscreenElement || document.body;
    parent.appendChild(prompt);
}

// Move the popup into or out of YouTube fullscreen.
document.addEventListener("fullscreenchange", () => {
    const prompt = document.getElementById("neurotech-rewind-prompt");

    if (prompt) {
        const parent = document.fullscreenElement || document.body;
        parent.appendChild(prompt);
    }
});


// Process commands from the desktop app
function handleCommand(action) {
    if (action === "prompt_rewind") {
        showRewindPrompt();
        return;
    }

    const video = getVideo();

    if (!video) {
        showStatus("YouTube video not found");
        return;
    }

    if (action === "distracted") {
        // Save only the first distraction timestamp
        if (savedDistractionTime === null && replay === null) {
            savedDistractionTime = video.currentTime;
            showStatus(
                `Distraction saved at ${savedDistractionTime.toFixed(1)}s`
            );
        }

    } else if (action === "focused") {
        // Keep the saved timestamp
        if (savedDistractionTime !== null) {
            showStatus(
                `Focus returned. Saved ${savedDistractionTime.toFixed(1)}s`
            );
        }

    } else if (action === "discard") {
        closeRewindPrompt();
        savedDistractionTime = null;
        showStatus("Distraction cleared");

    } else if (action === "rewind") {
        closeRewindPrompt();

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
    const currentId = new URL(location.href).searchParams.get("v");

    if (currentId !== videoId) {
        videoId = currentId;
        savedDistractionTime = null;
        replay = null;
        closeRewindPrompt();
        showStatus("New video loaded");
    }

    if (!replay) return;

    const video = getVideo();

    if (video !== replay.video) {
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
            return;
        }

        if (!connected) {
            showStatus("Connected to desktop app");
        }

        connected = true;
        lastEventId = response.data.last_id;

        for (const event of response.data.events) {
            handleCommand(event.action);
        }
    });
}

poll();
setInterval(poll, 250);
