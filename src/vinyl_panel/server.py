from __future__ import annotations

import argparse
import json
import mimetypes
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .paths import COVER_FILE, HOST, PORT, STATE_FILE, WEB_DIR
from .state import read_raw_state, read_state


def content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    if path.suffix == ".js":
        return "text/javascript"
    if path.suffix == ".css":
        return "text/css"
    return "application/octet-stream"


def asset_cache(path: Path) -> str:
    # Keep this project easy to iterate on while testing on Orange Pi.
    # Browser cache was making users see old app.js/styles.css until a hard refresh.
    if path.name == "index.html" or path.suffix in {".js", ".css"}:
        return "no-store"
    return "public, max-age=3600"


def state_version() -> str:
    try:
        stat = STATE_FILE.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"
    except FileNotFoundError:
        return "missing"


def path_status(path: Path) -> dict:
    exists = path.exists()
    parent = path.parent
    return {
        "path": str(path),
        "exists": exists,
        "is_file": path.is_file() if exists else False,
        "is_dir": path.is_dir() if exists else False,
        "size": path.stat().st_size if exists and path.is_file() else None,
        "parent_exists": parent.exists(),
        "parent_writable": os.access(parent, os.W_OK) if parent.exists() else False,
    }


def debug_payload() -> dict:
    state = read_state(STATE_FILE)
    raw = read_raw_state(STATE_FILE)
    return {
        "ok": state.get("event") != "error",
        "server_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "state_version": state_version(),
        "state": state,
        "raw_state": raw,
        "paths": {
            "state_file": path_status(STATE_FILE),
            "cover_file": path_status(COVER_FILE),
            "web_dir": path_status(WEB_DIR),
        },
    }


class VinylPanelHandler(BaseHTTPRequestHandler):
    server_version = "SpotifyVinylPanel/0.4"

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

                time.sleep(0.25)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/health":
            state = read_state(STATE_FILE)
            self.send_json(200, {"ok": state.get("event") != "error", "event": state.get("event"), "state_version": state_version()})
            return

        if route == "/api/debug":
            self.send_json(200, debug_payload())
            return

        if route == "/api/state/raw":
            self.send_json(200, read_raw_state(STATE_FILE))
            return

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

        self.send_bytes(200, target.read_bytes(), content_type(target), cache=asset_cache(target))


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
