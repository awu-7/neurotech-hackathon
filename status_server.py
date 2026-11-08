"""Single source of truth for NeuroLearn EEG UI state.
Start this before test.py and desktop_app.py: py status_server.py
"""
import threading
import time
from flask import Flask, jsonify, request
from sync_logging import get_logger

log = get_logger("server")
_last_status = None
_last_report = 0.0

app = Flask(__name__)
lock = threading.Lock()
state = {"status": "Waiting for EEG", "display": "Waiting for EEG", "ratio": None,
         "baseline": None, "updated_at": None, "revision": 0}
VALID = {"focused", "pending", "unfocused"}

@app.get("/health")
def health():
    return jsonify(ok=True, service="NeuroLearn EEG status server")

@app.route("/api/status", methods=["GET", "POST"])
def eeg_status():
    global _last_status, _last_report
    if request.method == "POST":
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or data.get("status") not in VALID:
            return jsonify(error="status must be focused, pending or unfocused"), 400
        display = data.get("display", data["status"])
        if not isinstance(display, str) or len(display) > 160:
            return jsonify(error="invalid display text"), 400
        with lock:
            state.update(status=data["status"], display=display,
                         ratio=data.get("ratio"), baseline=data.get("baseline"),
                         updated_at=time.time(), revision=state["revision"] + 1)
            result = dict(state)
        now = time.monotonic()
        if result["status"] != _last_status or now - _last_report >= 10:
            log.info("RECEIVED from test.py | revision=%s status=%s display=%r ratio=%s", result["revision"], result["status"], result["display"], result["ratio"])
            _last_status = result["status"]
            _last_report = now
        return jsonify(result)

    with lock:
        result = dict(state)
    result["live"] = result["updated_at"] is not None and time.time() - result["updated_at"] < 3.0
    return jsonify(result)

if __name__ == "__main__":
    log.info("SERVER STARTING http://127.0.0.1:5001 | health=/health | status=/api/status")
    app.run(host="127.0.0.1", port=5001, threaded=True, debug=False, use_reloader=False)
