from __future__ import annotations

import argparse
import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .paths import COVER_FILE, HOST, PORT, STATE_FILE, WEB_DIR
from .state import read_state


def content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    if path.suffix == ".js":
        return "text/javascript"
    if path.suffix == ".css":
        return "text/css"
    return "application/octet-stream"


def state_version() -> str:
    try:
        stat = STATE_FILE.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"
    except FileNotFoundError:
        return "missing"


class VinylPanelHandler(BaseHTTPRequestHandler):
    server_version = "SpotifyVinylPanel/0.2"

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def send_bytes(self, status: int, payload: bytes, mime: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status: int, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_bytes(status, payload, "application/json; charset=utf-8")

    def send_sse_event(self, event: str, data: dict | str) -> None:
        if isinstance(data, str):
            payload = data
        else:
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

        frame = f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
        self.wfile.write(frame)
        self.wfile.flush()

    def stream_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_version = ""
        last_ping = 0.0

        try:
            while True:
                current_version = state_version()
                now = time.monotonic()

                if current_version != last_version:
                    last_version = current_version
                    self.send_sse_event("state", read_state(STATE_FILE))
                    last_ping = now
                elif now - last_ping >= 15:
                    self.send_sse_event("ping", str(int(now)))
                    last_ping = now

                time.sleep(0.4)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/events":
            self.stream_events()
            return

        if route in ("/api/state", "/state.json"):
            self.send_json(200, read_state(STATE_FILE))
            return

        if route == "/cover.jpg":
            if COVER_FILE.exists():
                self.send_bytes(200, COVER_FILE.read_bytes(), "image/jpeg")
                return
            self.send_bytes(404, b"cover not found", "text/plain; charset=utf-8")
            return

        if route == "/":
            target = WEB_DIR / "index.html"
        else:
            safe = route.lstrip("/")
            target = (WEB_DIR / safe).resolve()
            try:
                target.relative_to(WEB_DIR.resolve())
            except ValueError:
                self.send_bytes(403, b"forbidden", "text/plain; charset=utf-8")
                return

        if not target.exists() or not target.is_file():
            self.send_bytes(404, b"not found", "text/plain; charset=utf-8")
            return

        cache = "no-store" if target.name == "index.html" else "public, max-age=3600"
        self.send_bytes(200, target.read_bytes(), content_type(target), cache=cache)


def main() -> None:
    parser = argparse.ArgumentParser(description="Orange Pi Spotify Vinyl Panel")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    print(f"Serving Spotify Vinyl Panel on http://{args.host}:{args.port}")
    print(f"Web dir: {WEB_DIR}")
    print(f"State file: {STATE_FILE}")
    ThreadingHTTPServer((args.host, args.port), VinylPanelHandler).serve_forever()


if __name__ == "__main__":
    main()
