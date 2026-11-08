"""Nonblocking best-effort sender from test.py to Flask (stdlib only)."""
import json
import queue
import threading
from urllib.request import Request, urlopen
from urllib.error import URLError
import time
from sync_logging import get_logger

log = get_logger("test_sender")

SERVER = "http://127.0.0.1:5001/api/status"
_pending = queue.Queue(maxsize=1)
_started = False
_start_lock = threading.Lock()

def _worker():
    warned = False
    last_status = None
    last_report = 0.0
    while True:
        event = _pending.get()
        try:
            body = json.dumps(event).encode("utf-8")
            req = Request(SERVER, data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=0.6) as resp:
                resp.read()
            now = time.monotonic()
            if warned:
                log.info("SERVER RECONNECTED")
            if warned or event["status"] != last_status or now - last_report >= 10:
                log.info("SENT to Flask | status=%s display=%r ratio=%s", event["status"], event["display"], event["ratio"])
                last_status = event["status"]
                last_report = now
            warned = False
        except (OSError, URLError) as exc:
            if not warned:
                log.error("FAILED to send to Flask %s | %s", SERVER, exc)
            warned = True

def publish_status(status, display, ratio=None, baseline=None):
    global _started
    with _start_lock:
        if not _started:
            threading.Thread(target=_worker, daemon=True, name="EEG-Flask-Publisher").start()
            _started = True
    event = {"status": status, "display": display,
             "ratio": ratio, "baseline": baseline}
    try:
        _pending.put_nowait(event)
    except queue.Full:
        try:
            _pending.get_nowait()
        except queue.Empty:
            pass
        try:
            _pending.put_nowait(event)
        except queue.Full:
            pass
