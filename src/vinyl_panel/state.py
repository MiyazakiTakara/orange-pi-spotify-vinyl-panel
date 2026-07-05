from __future__ import annotations

import json
from pathlib import Path
from typing import Any

KNOWN_PLAYBACK_EVENTS = {"playing", "paused", "stopped", "waiting", "error"}
PLAYING_ALIASES = {"seeked", "changed", "metadata", "track_changed", "unavailable", "unknown", "resumed", "volume_set"}
PAUSED_ALIASES = {"pause"}
STOPPED_ALIASES = {"end_of_track", "session_disconnected", "inactive"}

EMPTY_STATE: dict[str, Any] = {
    "schema_version": 2,
    "event": "waiting",
    "raw_event": "waiting",
    "track_id": "",
    "old_track_id": "",
    "spotify_url": "",
    "title": "",
    "author": "",
    "thumbnail_url": "",
    "local_thumbnail_url": "",
    "provider": "",
    "oembed_error": "",
    "updated_at": "",
    "state_updated_at": "",
    "playback_updated_at": "",
    "metadata_updated_at": "",
    "position_ms": "",
    "duration_ms": "",
    "volume": "",
    "shuffle": "",
    "repeat": "",
}


def normalize_event(raw_event: Any, has_track: bool, previous_event: str = "playing") -> str:
    event = str(raw_event or "unknown").lower()
    previous = str(previous_event or "playing").lower()

    if event in KNOWN_PLAYBACK_EVENTS:
        return event
    if event in PAUSED_ALIASES:
        return "paused"
    if event in STOPPED_ALIASES:
        return "stopped"
    if event in PLAYING_ALIASES:
        if previous in {"paused", "stopped", "waiting"} and event in {"metadata", "changed"}:
            return previous
        return "playing" if has_track else previous
    return "playing" if has_track else "waiting"


def read_raw_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return dict(EMPTY_STATE)

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        state = dict(EMPTY_STATE)
        state["event"] = "error"
        state["raw_event"] = "read_error"
        state["error"] = str(exc)
        return state

    if not isinstance(data, dict):
        state = dict(EMPTY_STATE)
        state["event"] = "error"
        state["raw_event"] = "invalid_state"
        state["error"] = "state file does not contain a JSON object"
        return state

    return data


def normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    state = dict(EMPTY_STATE)
    state.update(data)

    raw_event = state.get("raw_event") or state.get("event") or "unknown"
    previous_event = str(state.get("previous_event") or state.get("event") or "playing")
    has_track = bool(state.get("track_id") or state.get("title"))
    state["event"] = normalize_event(raw_event, has_track, previous_event)
    state["raw_event"] = str(raw_event)

    # Backward compatibility for older state files.
    if not state.get("state_updated_at"):
        state["state_updated_at"] = state.get("updated_at", "")
    if not state.get("playback_updated_at"):
        state["playback_updated_at"] = state.get("updated_at", "")
    if not state.get("metadata_updated_at"):
        state["metadata_updated_at"] = state.get("updated_at", "")

    state["schema_version"] = 2
    return state


def read_state(path: Path) -> dict[str, Any]:
    return normalize_state(read_raw_state(path))
