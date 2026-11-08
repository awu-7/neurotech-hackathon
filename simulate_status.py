"""Manual end-to-end Flask status test; close test.py before running."""
import json
import time
from urllib.request import Request, urlopen

url = "http://127.0.0.1:5001/api/status"
states = [
    ("focused", "Focused"),
    ("pending", "Unfocused Pending (3.0s / 15s)"),
    ("unfocused", "⚠️ UNFOCUSED ALERT"),
    ("focused", "Focused"),
]
for status, display in states:
    data = json.dumps({"status": status, "display": display, "ratio": 2.1, "baseline": 1.0}).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=3) as resp:
        result = json.load(resp)
    print(f"Sent {status!r}; server revision={result['revision']}; watch the desktop")
    time.sleep(2)
