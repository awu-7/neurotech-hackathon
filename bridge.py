
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

commands = []
commands_lock = threading.Lock()


def send_command(action):
    with commands_lock:
        commands.append({
            "id": len(commands) + 1,
            "action": action
        })


class BridgeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path != "/events":
            self.send_error(404)
            return

        try:
            after = int(parse_qs(parsed.query).get("after", ["0"])[0])
        except ValueError:
            self.send_error(400)
            return

        with commands_lock:
            latest_id = len(commands)

            if after == -1:
                events = []
            else:
                events = [
                    c for c in commands if c["id"] > after
                ]

        body = json.dumps({
            "last_id": latest_id,
            "events": events
        }).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def start_bridge():
    server = ThreadingHTTPServer(
        ("127.0.0.1", 8765),
        BridgeHandler
    )

    threading.Thread(
        target=server.serve_forever,
        daemon=True
    ).start()
