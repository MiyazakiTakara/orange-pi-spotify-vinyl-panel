from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .paths import COVER_FILE, HOST, PORT, WEB_DIR
from .state import read_state
from .paths import STATE_FILE


def content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    if path.suffix == ".js":
        return "text/javascript"
    if path.suffix == ".css":
        return "text/css"
    return "application/octet-stream"


class VinylPanelHandler(BaseHTTPRequestHandler):
    server_version = "SpotifyVinylPanel/0.1"

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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

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
