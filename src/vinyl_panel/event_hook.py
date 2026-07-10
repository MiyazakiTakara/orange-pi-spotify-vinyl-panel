from __future__ import annotations

import copy
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .paths import LAST_GOOD_FILE, LOCK_FILE, STATE_FILE
from .state import empty_state, empty_track, normalize_state

TRACK_METADATA_EVENT = "track_changed"
PENDING_EVENTS = {"loading", "preloading", "preload_next"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def env_text(env: Mapping[str, str], key: str) -> str:
    return str(env.get(key, "") or "")


def env_int(env: Mapping[str, str], key: str, default: int = 0) -> int:
    try:
        return int(env_text(env, key))
    except ValueError:
        return default


def env_bool(env: Mapping[str, str], key: str) -> bool:
    return env_text(env, key).lower() in {"1", "true", "yes", "on"}


def split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def local_cover_url(track_id: str) -> str:
    return f"/covers/{track_id}.jpg" if track_id else ""


def track_from_env(env: Mapping[str, str], existing: Mapping[str, Any] | None = None) -> dict[str, Any]:
    track = copy.deepcopy(dict(existing or empty_track()))
    track_id = env_text(env, "TRACK_ID") or str(track.get("id") or "")
    artists = split_lines(env_text(env, "ARTISTS")) or list(track.get("artists") or [])
    covers = split_lines(env_text(env, "COVERS"))

    if track_id:
        track["id"] = track_id
        track["uri"] = env_text(env, "URI") or str(track.get("uri") or f"spotify:track:{track_id}")
        track["spotify_url"] = f"https://open.spotify.com/track/{track_id}"
        track["cover_local_url"] = local_cover_url(track_id)

    if env_text(env, "NAME"):
        track["name"] = env_text(env, "NAME")
    if artists:
        track["artists"] = artists
        track["artist_text"] = ", ".join(artists)
    if env_text(env, "ALBUM"):
        track["album"] = env_text(env, "ALBUM")
    if env_text(env, "DURATION_MS"):
        track["duration_ms"] = max(0, env_int(env, "DURATION_MS"))
    if covers:
        track["cover_url"] = covers[0]
    if env_text(env, "ITEM_TYPE"):
        track["item_type"] = env_text(env, "ITEM_TYPE")
    if env_text(env, "IS_EXPLICIT"):
        track["is_explicit"] = env_bool(env, "IS_EXPLICIT")

    return track


def append_event(state: dict[str, Any], event: str, timestamp: str, env: Mapping[str, str]) -> None:
    history = list(state.get("last_events") or [])
    history.append(
        {
            "event": event,
            "at": timestamp,
            "track_id": env_text(env, "TRACK_ID"),
            "position_ms": env_text(env, "POSITION_MS"),
        }
    )
    state["last_events"] = history[-20:]


def promote_track(state: dict[str, Any], track_id: str, env: Mapping[str, str]) -> None:
    current = state["current_track"]
    pending = state["pending_track"]

    if current.get("id") == track_id:
        state["current_track"] = track_from_env(env, current)
        return

    if pending.get("id") == track_id:
        state["current_track"] = track_from_env(env, pending)
    else:
        state["current_track"] = track_from_env(env, {"id": track_id})

    if state["pending_track"].get("id") == track_id:
        state["pending_track"] = empty_track()


def apply_event(previous: Mapping[str, Any] | None, env: Mapping[str, str], timestamp: str | None = None) -> dict[str, Any]:
    state = normalize_state(copy.deepcopy(dict(previous or empty_state())))
    for key in (
        "event",
        "track_id",
        "spotify_url",
        "title",
        "author",
        "thumbnail_url",
        "local_thumbnail_url",
        "position_ms",
        "duration_ms",
        "playback_updated_at",
        "state_updated_at",
        "volume",
        "shuffle",
        "repeat",
    ):
        state.pop(key, None)

    timestamp = timestamp or now_iso()
    event = env_text(env, "PLAYER_EVENT").lower() or "unknown"
    track_id = env_text(env, "TRACK_ID")

    state["schema_version"] = 3
    state["revision"] = int(state.get("revision") or 0) + 1
    state["updated_at"] = timestamp
    state["raw_event"] = event
    state["last_error"] = ""
    append_event(state, event, timestamp, env)

    playback = state["playback"]
    current = state["current_track"]
    pending = state["pending_track"]

    if event == TRACK_METADATA_EVENT:
        metadata = track_from_env(env, pending if pending.get("id") == track_id else None)
        if current.get("id") == track_id:
            state["current_track"] = track_from_env(env, current)
            playback["duration_ms"] = state["current_track"].get("duration_ms", 0)
        else:
            state["pending_track"] = metadata

    elif event in PENDING_EVENTS:
        if track_id and track_id != current.get("id"):
            state["pending_track"] = track_from_env(env, pending if pending.get("id") == track_id else {"id": track_id})

    elif event in {"playing", "paused"}:
        if track_id:
            promote_track(state, track_id, env)
        current = state["current_track"]
        playback["status"] = event
        playback["position_ms"] = max(0, env_int(env, "POSITION_MS", int(playback.get("position_ms") or 0)))
        playback["duration_ms"] = max(0, int(current.get("duration_ms") or playback.get("duration_ms") or 0))
        playback["updated_at"] = timestamp

    elif event in {"seeked", "position_correction"}:
        if track_id and track_id != current.get("id"):
            promote_track(state, track_id, env)
        playback["position_ms"] = max(0, env_int(env, "POSITION_MS", int(playback.get("position_ms") or 0)))
        playback["updated_at"] = timestamp
        if playback.get("status") not in {"playing", "paused"}:
            playback["status"] = "playing"

    elif event == "stopped":
        playback["status"] = "stopped"
        playback["updated_at"] = timestamp

    elif event == "end_of_track":
        playback["status"] = "stopped"
        if playback.get("duration_ms"):
            playback["position_ms"] = playback["duration_ms"]
        playback["updated_at"] = timestamp

    elif event == "unavailable":
        state["last_error"] = f"Track unavailable: {track_id}" if track_id else "Track unavailable"

    elif event == "volume_changed":
        state["controls"]["volume"] = env_text(env, "VOLUME")

    elif event == "shuffle_changed":
        state["controls"]["shuffle"] = env_text(env, "SHUFFLE")

    elif event == "repeat_changed":
        state["controls"]["repeat"] = env_text(env, "REPEAT")
        state["controls"]["repeat_track"] = env_text(env, "REPEAT_TRACK")

    elif event == "auto_play_changed":
        state["controls"]["auto_play"] = env_text(env, "AUTO_PLAY")

    elif event == "session_connected":
        state["session"]["connected"] = True
        state["session"]["user_name"] = env_text(env, "USER_NAME")

    elif event == "session_disconnected":
        state["session"]["connected"] = False

    elif event == "session_client_changed":
        state["session"]["client_name"] = env_text(env, "CLIENT_NAME")
        state["session"]["client_brand"] = env_text(env, "CLIENT_BRAND_NAME")
        state["session"]["client_model"] = env_text(env, "CLIENT_MODEL_NAME")

    elif event == "sink":
        state["sink_status"] = env_text(env, "SINK_STATUS")

    return state


def read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def main() -> int:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_FILE.open("a+", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            previous = read_json(STATE_FILE) or read_json(LAST_GOOD_FILE) or empty_state()
            state = apply_event(previous, os.environ)
            write_json_atomic(STATE_FILE, state)
            if state.get("current_track", {}).get("id"):
                write_json_atomic(LAST_GOOD_FILE, state)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
