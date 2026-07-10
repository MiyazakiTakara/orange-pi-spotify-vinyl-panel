from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(os.getenv("SPOTIFY_PANEL_DIR", "/opt/spotify-panel"))
WEB_DIR = Path(os.getenv("SPOTIFY_PANEL_WEB_DIR", str(APP_DIR / "web")))
STATE_FILE = Path(os.getenv("SPOTIFY_PANEL_STATE", str(APP_DIR / "state.json")))
LAST_GOOD_FILE = Path(os.getenv("SPOTIFY_PANEL_LAST_GOOD", str(APP_DIR / "last-good-state.json")))
LOCK_FILE = Path(os.getenv("SPOTIFY_PANEL_LOCK", str(APP_DIR / "state.lock")))
COVERS_DIR = Path(os.getenv("SPOTIFY_PANEL_COVERS", str(APP_DIR / "covers")))
HOST = os.getenv("SPOTIFY_PANEL_HOST", "0.0.0.0")
PORT = int(os.getenv("SPOTIFY_PANEL_PORT", "8080"))
