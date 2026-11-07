
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type !== "poll") return;

    fetch(`http://127.0.0.1:8765/events?after=${message.after}`, {
        cache: "no-store"
    })
        .then((response) => {
            if (!response.ok) {
                throw new Error("Desktop bridge is unavailable");
            }
            return response.json();
        })
        .then((data) => sendResponse({ ok: true, data }))
        .catch((error) => {
            sendResponse({ ok: false, error: error.message });
        });

    return true;
});
