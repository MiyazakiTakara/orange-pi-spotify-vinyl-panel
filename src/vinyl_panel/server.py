from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .paths import COVERS_DIR, HOST, PORT, STATE_FILE, WEB_DIR
from .state import read_raw_state, read_state

TRACK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed
    if path.suffix == ".js":
        return "text/javascript"
    if path.suffix == ".css":
        return "text/css"
    return "application/octet-stream"


def file_version(path: Path) -> str:
    try:
        stat = path.stat()
        return f"{stat.st_mtime_ns}:{stat.st_size}"
    except FileNotFoundError:
        return "missing"


def make_etag(path: Path) -> str:
    version = file_version(path).encode("utf-8")
    return '"' + hashlib.sha1(version).hexdigest() + '"'


def json_bytes(data: Any, pretty: bool = False) -> bytes:
    if pretty:
        return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def path_status(path: Path) -> dict[str, Any]:
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


class CoverCache:
    def __init__(self, covers_dir: Path) -> None:
        self.covers_dir = covers_dir
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cover-cache")
        self._lock = threading.Lock()
        self._scheduled: set[str] = set()

    def path_for(self, track_id: str) -> Path | None:
        if not TRACK_ID_RE.fullmatch(track_id):
            return None
        return self.covers_dir / f"{track_id}.jpg"

    def remote_url_for(self, state: dict[str, Any], track_id: str) -> str:
        for key in ("current_track", "pending_track"):
            track = state.get(key) or {}
            if track.get("id") == track_id:
                return str(track.get("cover_url") or "")
        return ""

    def schedule_track(self, track: dict[str, Any]) -> None:
        track_id = str(track.get("id") or "")
        remote_url = str(track.get("cover_url") or "")
        path = self.path_for(track_id)
        if not path or not remote_url or path.exists():
            return

        with self._lock:
            if track_id in self._scheduled:
                return
            self._scheduled.add(track_id)

        future = self.executor.submit(self._download, track_id, remote_url)
        future.add_done_callback(lambda _: self._clear_scheduled(track_id))

    def schedule_state(self, state: dict[str, Any]) -> None:
        for key in ("current_track", "pending_track"):
            track = state.get(key)
            if isinstance(track, dict):
                self.schedule_track(track)

    def ensure(self, track_id: str, remote_url: str) -> Path | None:
        path = self.path_for(track_id)
        if not path:
            return None
        if path.exists():
            return path
        if remote_url:
            self._download(track_id, remote_url)
        return path if path.exists() else None

    def _clear_scheduled(self, track_id: str) -> None:
        with self._lock:
            self._scheduled.discard(track_id)

    def _download(self, track_id: str, remote_url: str) -> None:
        path = self.path_for(track_id)
        if not path or path.exists() or not remote_url.startswith(("https://", "http://")):
            return

        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            request = urllib.request.Request(
                remote_url,
                headers={"User-Agent": "OrangePiSpotifyVinylPanel/1.0"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                payload = response.read(8 * 1024 * 1024 + 1)
                content_type_header = response.headers.get_content_type()
            if not payload or len(payload) > 8 * 1024 * 1024:
                return
            if not content_type_header.startswith("image/"):
                return
            tmp.write_bytes(payload)
            os.replace(tmp, path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


class StateBroker:
    def __init__(self, state_file: Path, cover_cache: CoverCache) -> None:
        self.state_file = state_file
        self.cover_cache = cover_cache
        self._condition = threading.Condition()
        self._revision = 0
        self._version = ""
        self._state = read_state(state_file)
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, name="state-broker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        with self._condition:
            self._condition.notify_all()

    def snapshot(self) -> tuple[int, dict[str, Any]]:
        with self._condition:
            return self._revision, dict(self._state)

    def wait_for_change(self, after_revision: int, timeout: float) -> tuple[int, dict[str, Any]]:
        with self._condition:
            if self._revision <= after_revision and self._running:
                self._condition.wait(timeout=timeout)
            return self._revision, dict(self._state)

    def _watch_loop(self) -> None:
        while self._running:
            version = file_version(self.state_file)
            if version != self._version:
                state = read_state(self.state_file)
                self.cover_cache.schedule_state(state)
                with self._condition:
                    self._version = version
                    self._state = state
                    self._revision += 1
                    self._condition.notify_all()
            time.sleep(0.2)


class PanelHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], handler: type[BaseHTTPRequestHandler]) -> None:
        self.cover_cache = CoverCache(COVERS_DIR)
        self.broker = StateBroker(STATE_FILE, self.cover_cache)
        super().__init__(server_address, handler)


class VinylPanelHandler(BaseHTTPRequestHandler):
    server_version = "SpotifyVinylPanel/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def panel_server(self) -> PanelHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), fmt % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        super().end_headers()

    def send_bytes(
        self,
        status: int,
        payload: bytes,
        mime: str,
        *,
        cache: str = "no-store",
        etag: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def send_json(self, status: int, data: Any, *, pretty: bool = False) -> None:
        self.send_bytes(status, json_bytes(data, pretty=pretty), "application/json; charset=utf-8")

    def send_file(self, path: Path, *, cache: str) -> None:
        etag = make_etag(path)
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("Cache-Control", cache)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_bytes(200, path.read_bytes(), content_type(path), cache=cache, etag=etag)

    def stream_events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            revision = -1
            while True:
                new_revision, state = self.panel_server.broker.wait_for_change(revision, timeout=15.0)
                if new_revision != revision:
                    revision = new_revision
                    payload = dict(state)
                    payload["server_revision"] = revision
                    frame = b"event: state\ndata: " + json_bytes(payload) + b"\n\n"
                else:
                    frame = b"event: ping\ndata: {}\n\n"
                self.wfile.write(frame)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, TimeoutError, OSError):
            return

    def state_payload(self) -> dict[str, Any]:
        revision, state = self.panel_server.broker.snapshot()
        payload = dict(state)
        payload["server_revision"] = revision
        return payload

    def debug_payload(self) -> dict[str, Any]:
        state = self.state_payload()
        return {
            "ok": state.get("playback", {}).get("status") != "error",
            "server_time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "state_file_version": file_version(STATE_FILE),
            "state": state,
            "raw_state": read_raw_state(STATE_FILE),
            "paths": {
                "state_file": path_status(STATE_FILE),
                "covers_dir": path_status(COVERS_DIR),
                "web_dir": path_status(WEB_DIR),
            },
        }

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = unquote(parsed.path)

        if route == "/health":
            state = self.state_payload()
            self.send_json(
                200,
                {
                    "ok": state.get("playback", {}).get("status") != "error",
                    "status": state.get("playback", {}).get("status", "waiting"),
                    "revision": state.get("server_revision", 0),
                },
            )
            return

        if route == "/api/debug":
            self.send_json(200, self.debug_payload(), pretty=True)
            return

        if route == "/api/state/raw":
            self.send_json(200, read_raw_state(STATE_FILE), pretty=True)
            return

        if route == "/api/events":
            self.stream_events()
            return

        if route in ("/api/state", "/state.json"):
            self.send_json(200, self.state_payload())
            return

        if route.startswith("/covers/") and route.endswith(".jpg"):
            track_id = route.removeprefix("/covers/").removesuffix(".jpg")
            path = self.panel_server.cover_cache.path_for(track_id)
            if path and not path.exists():
                state = self.state_payload()
                remote_url = self.panel_server.cover_cache.remote_url_for(state, track_id)
                path = self.panel_server.cover_cache.ensure(track_id, remote_url)
            if path and path.exists():
                self.send_file(path, cache="public, max-age=31536000, immutable")
            else:
                self.send_bytes(404, b"cover not found", "text/plain; charset=utf-8")
            return

        if route == "/":
            target = WEB_DIR / "index.html"
        else:
            target = (WEB_DIR / route.lstrip("/")).resolve()
            try:
                target.relative_to(WEB_DIR.resolve())
            except ValueError:
                self.send_bytes(403, b"forbidden", "text/plain; charset=utf-8")
                return

        if not target.exists() or not target.is_file():
            self.send_bytes(404, b"not found", "text/plain; charset=utf-8")
            return

        cache = "no-cache" if target.name == "index.html" or target.suffix in {".js", ".css"} else "public, max-age=3600"
        self.send_file(target, cache=cache)


def main() -> None:
    parser = argparse.ArgumentParser(description="Orange Pi Spotify Vinyl Panel")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    server = PanelHTTPServer((args.host, args.port), VinylPanelHandler)
    server.broker.start()
    print(f"Serving Spotify Vinyl Panel on http://{args.host}:{args.port}")
    print(f"Web dir: {WEB_DIR}")
    print(f"State file: {STATE_FILE}")
    print(f"Covers dir: {COVERS_DIR}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.broker.stop()
        server.server_close()


if __name__ == "__main__":
    main()
