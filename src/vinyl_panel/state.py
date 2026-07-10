from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3
PLAYBACK_STATUSES = {"playing", "paused", "stopped", "waiting", "error"}


def empty_track() -> dict[str, Any]:
    return {
        "id": "",
        "uri": "",
        "spotify_url": "",
        "name": "",
        "artists": [],
        "artist_text": "",
        "album": "",
        "duration_ms": 0,
        "cover_url": "",
        "cover_local_url": "",
        "item_type": "Track",
        "is_explicit": False,
    }


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "updated_at": "",
        "raw_event": "waiting",
        "playback": {
            "status": "waiting",
            "position_ms": 0,
            "duration_ms": 0,
            "updated_at": "",
        },
        "current_track": empty_track(),
        "pending_track": empty_track(),
        "controls": {
            "volume": "",
            "shuffle": "",
            "repeat": "",
            "repeat_track": "",
            "auto_play": "",
        },
        "session": {
            "connected": False,
            "user_name": "",
            "client_name": "",
            "client_brand": "",
            "client_model": "",
        },
        "sink_status": "",
        "last_error": "",
        "last_events": [],
    }


def _number(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_track(value: Any) -> dict[str, Any]:
    track = empty_track()
    if isinstance(value, dict):
        track.update(value)

    artists = track.get("artists", [])
    if isinstance(artists, str):
        artists = [part.strip() for part in artists.split("\n") if part.strip()]
    elif not isinstance(artists, list):
        artists = []

    track["artists"] = [str(item) for item in artists if str(item).strip()]
    track["artist_text"] = str(track.get("artist_text") or ", ".join(track["artists"]))
    track["duration_ms"] = max(0, _number(track.get("duration_ms")))
    track["is_explicit"] = _bool(track.get("is_explicit"))

    for key in ("id", "uri", "spotify_url", "name", "album", "cover_url", "cover_local_url", "item_type"):
        track[key] = str(track.get(key) or "")

    return track


def normalize_state(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        state = empty_state()
        state["playback"]["status"] = "error"
        state["raw_event"] = "invalid_state"
        state["last_error"] = "state file does not contain a JSON object"
        return add_legacy_fields(state)

    if _number(data.get("schema_version")) >= SCHEMA_VERSION and isinstance(data.get("playback"), dict):
        state = empty_state()
        state.update(copy.deepcopy(data))
        state["schema_version"] = SCHEMA_VERSION
        state["revision"] = max(0, _number(state.get("revision")))
        state["current_track"] = normalize_track(state.get("current_track"))
        state["pending_track"] = normalize_track(state.get("pending_track"))

        playback = dict(empty_state()["playback"])
        playback.update(state.get("playback") or {})
        status = str(playback.get("status") or "waiting").lower()
        playback["status"] = status if status in PLAYBACK_STATUSES else "waiting"
        playback["position_ms"] = max(0, _number(playback.get("position_ms")))
        playback["duration_ms"] = max(
            0,
            _number(playback.get("duration_ms"), state["current_track"].get("duration_ms", 0)),
        )
        playback["updated_at"] = str(playback.get("updated_at") or state.get("updated_at") or "")
        state["playback"] = playback

        controls = dict(empty_state()["controls"])
        if isinstance(state.get("controls"), dict):
            controls.update(state["controls"])
        state["controls"] = controls

        session = dict(empty_state()["session"])
        if isinstance(state.get("session"), dict):
            session.update(state["session"])
        state["session"] = session

        events = state.get("last_events")
        state["last_events"] = events[-20:] if isinstance(events, list) else []
        return add_legacy_fields(state)

    state = empty_state()
    status = str(data.get("event") or "waiting").lower()
    if status not in PLAYBACK_STATUSES:
        status = "playing" if data.get("track_id") or data.get("title") else "waiting"

    artists = []
    if data.get("author"):
        artists = [str(data["author"])]

    track = normalize_track(
        {
            "id": data.get("track_id", ""),
            "uri": "",
            "spotify_url": data.get("spotify_url", ""),
            "name": data.get("title", ""),
            "artists": artists,
            "artist_text": data.get("author", ""),
            "duration_ms": data.get("duration_ms", 0),
            "cover_url": data.get("thumbnail_url", ""),
            "cover_local_url": data.get("local_thumbnail_url", ""),
        }
    )

    state.update(
        {
            "revision": 1,
            "updated_at": str(data.get("state_updated_at") or data.get("updated_at") or ""),
            "raw_event": str(data.get("raw_event") or data.get("event") or "unknown"),
            "current_track": track,
            "last_error": str(data.get("oembed_error") or data.get("error") or ""),
        }
    )
    state["playback"] = {
        "status": status,
        "position_ms": max(0, _number(data.get("position_ms"))),
        "duration_ms": track["duration_ms"],
        "updated_at": str(data.get("playback_updated_at") or data.get("updated_at") or ""),
    }
    state["controls"].update(
        {
            "volume": data.get("volume", ""),
            "shuffle": data.get("shuffle", ""),
            "repeat": data.get("repeat", ""),
        }
    )
    return add_legacy_fields(state)


def add_legacy_fields(state: dict[str, Any]) -> dict[str, Any]:
    current = state.get("current_track") or empty_track()
    playback = state.get("playback") or empty_state()["playback"]
    controls = state.get("controls") or empty_state()["controls"]

    state["event"] = playback.get("status", "waiting")
    state["track_id"] = current.get("id", "")
    state["spotify_url"] = current.get("spotify_url", "") or (
        f"https://open.spotify.com/track/{current.get('id')}" if current.get("id") else ""
    )
    state["title"] = current.get("name", "")
    state["author"] = current.get("artist_text", "")
    state["thumbnail_url"] = current.get("cover_url", "")
    state["local_thumbnail_url"] = current.get("cover_local_url", "")
    state["position_ms"] = playback.get("position_ms", 0)
    state["duration_ms"] = playback.get("duration_ms", current.get("duration_ms", 0))
    state["playback_updated_at"] = playback.get("updated_at", "")
    state["state_updated_at"] = state.get("updated_at", "")
    state["volume"] = controls.get("volume", "")
    state["shuffle"] = controls.get("shuffle", "")
    state["repeat"] = controls.get("repeat", "")
    return state


def read_raw_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        state = empty_state()
        state["playback"]["status"] = "error"
        state["raw_event"] = "read_error"
        state["last_error"] = str(exc)
        return state

    return data if isinstance(data, dict) else {"invalid_state": data}


def read_state(path: Path) -> dict[str, Any]:
    return normalize_state(read_raw_state(path))
