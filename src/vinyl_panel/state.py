from __future__ import annotations

import json
from pathlib import Path
from typing import Any

EMPTY_STATE: dict[str, Any] = {
    "event": "waiting",
    "track_id": "",
    "spotify_url": "",
    "title": "",
    "author": "",
    "thumbnail_url": "",
    "local_thumbnail_url": "",
    "updated_at": "",
    "position_ms": "",
    "duration_ms": "",
    "volume": "",
    "shuffle": "",
    "repeat": "",
}


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(EMPTY_STATE)

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        state = dict(EMPTY_STATE)
        state["event"] = "error"
        state["error"] = str(exc)
        return state

    state = dict(EMPTY_STATE)
    if isinstance(data, dict):
        state.update(data)
    return state
