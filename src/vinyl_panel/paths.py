from __future__ import annotations

import os
from pathlib import Path

APP_DIR = Path(os.getenv("SPOTIFY_PANEL_DIR", "/opt/spotify-panel"))
WEB_DIR = Path(os.getenv("SPOTIFY_PANEL_WEB_DIR", str(APP_DIR / "web")))
STATE_FILE = Path(os.getenv("SPOTIFY_PANEL_STATE", str(APP_DIR / "state.json")))
COVER_FILE = Path(os.getenv("SPOTIFY_PANEL_COVER", str(APP_DIR / "cover.jpg")))
HOST = os.getenv("SPOTIFY_PANEL_HOST", "0.0.0.0")
PORT = int(os.getenv("SPOTIFY_PANEL_PORT", "8080"))
