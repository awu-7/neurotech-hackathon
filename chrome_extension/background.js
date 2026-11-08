// Route playback to the selected lecture tab, even when the desktop has focus.
let ownerTab = null;
let lastDistractionId = null;
const routingReady = chrome.storage.session.get(["ownerTab", "lastDistractionId"]).then(saved => {
    ownerTab = saved.ownerTab ?? null;
    lastDistractionId = saved.lastDistractionId ?? null;
});
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (!sender.tab || !["poll", "saveInterval"].includes(message.type)) return;
    (async () => {
        await routingReady;
        if (message.type === "saveInterval") {
            const response = await fetch("http://127.0.0.1:5001/api/distractions", {
                method: "POST", headers: {"Content-Type": "application/json"},
                body: JSON.stringify(message.interval), signal: AbortSignal.timeout(5000)
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Interval could not be saved");
            return {ok: true, data};
        }
        const response = await fetch(`http://127.0.0.1:8765/events?after=${Number(message.after)}`, {
            cache: "no-store", signal: AbortSignal.timeout(3000)
        });
        if (!response.ok) throw new Error("Desktop bridge is unavailable");
        const data = await response.json();
        const [active] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
        data.events = data.events.filter(event => {
            const eventKey = `${data.session}:${event.id}`;
            if (event.action === "distracted" && eventKey !== lastDistractionId) {
                lastDistractionId = eventKey;
                ownerTab = active?.id;
            }
            return sender.tab.id === ownerTab;
        });
        await chrome.storage.session.set({ownerTab, lastDistractionId});
        return {ok: true, data};
    })().then(sendResponse).catch(error => sendResponse({ok: false, error: error.message}));
    return true;
});
