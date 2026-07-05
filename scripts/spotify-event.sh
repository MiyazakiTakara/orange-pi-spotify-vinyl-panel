#!/usr/bin/env bash
# This script is executed by librespot --onevent. It must never break playback.
set +e

STATE_DIR="${SPOTIFY_PANEL_DIR:-/opt/spotify-panel}"
STATE_FILE="${SPOTIFY_PANEL_STATE:-$STATE_DIR/state.json}"
ENV_LOG="${SPOTIFY_PANEL_ENV_LOG:-$STATE_DIR/last-event.env}"
COVER_FILE="${SPOTIFY_PANEL_COVER:-$STATE_DIR/cover.jpg}"
LAST_GOOD_FILE="${SPOTIFY_PANEL_LAST_GOOD:-$STATE_DIR/last-good-state.json}"

mkdir -p "$STATE_DIR" 2>/dev/null || true
env | sort > "$ENV_LOG" 2>/dev/null || true
NOW="$(date -Is)"
export NOW

python3 - "$STATE_FILE" "$COVER_FILE" "$LAST_GOOD_FILE" <<'PY'
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

state_file = Path(sys.argv[1])
cover_file = Path(sys.argv[2])
last_good_file = Path(sys.argv[3])
state_dir = state_file.parent

try:
    state_dir.mkdir(parents=True, exist_ok=True)
except Exception:
    sys.exit(0)


def read_json(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json_atomic(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def env_value(name):
    return os.environ.get(name, "")


def env_or_old(name, old, key):
    value = env_value(name)
    return value if value != "" else old.get(key, "")


def normalize_event(raw_event, old, has_track):
    event = (raw_event or "unknown").lower()
    old_event = str(old.get("event", "playing")).lower()

    if event in {"playing", "paused", "stopped", "waiting", "error"}:
        return event
    if event in {"pause"}:
        return "paused"
    if event in {"end_of_track", "session_disconnected", "inactive"}:
        return "stopped"
    if event in {"seeked", "volume_set"}:
        return "paused" if old_event == "paused" else "playing"
    if event in {"changed", "metadata", "track_changed", "unavailable", "unknown", "resumed"}:
        if old_event in {"paused", "stopped", "waiting"} and event in {"metadata", "changed"}:
            return old_event
        return "playing" if has_track else old_event
    return "playing" if has_track else "waiting"


def spotify_track_url(track_id):
    clean_id = track_id.split(":")[-1] if track_id.startswith("spotify:track:") else track_id
    return clean_id, ("https://open.spotify.com/track/" + clean_id if clean_id else "")


def fetch_metadata(spotify_url, clean_id):
    if not spotify_url:
        return {}, ""

    try:
        oembed_url = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(spotify_url, safe="")
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "OrangePiSpotifyVinylPanel/0.2"})
        with urllib.request.urlopen(req, timeout=8) as response:
            meta = json.loads(response.read().decode("utf-8"))

        thumbnail_url = meta.get("thumbnail_url", "")
        local_thumbnail_url = ""

        if thumbnail_url:
            try:
                img_req = urllib.request.Request(thumbnail_url, headers={"User-Agent": "OrangePiSpotifyVinylPanel/0.2"})
                with urllib.request.urlopen(img_req, timeout=12) as img_response:
                    image_data = img_response.read()
                tmp_cover = cover_file.with_name(cover_file.name + ".tmp")
                with tmp_cover.open("wb") as handle:
                    handle.write(image_data)
                os.replace(tmp_cover, cover_file)
                local_thumbnail_url = "/cover.jpg?track=" + clean_id
            except Exception:
                local_thumbnail_url = ""

        return {
            "title": meta.get("title", ""),
            "author": meta.get("author_name", ""),
            "thumbnail_url": thumbnail_url,
            "local_thumbnail_url": local_thumbnail_url,
            "provider": meta.get("provider_name", ""),
        }, ""
    except Exception as exc:
        return {}, str(exc)


old = read_json(state_file)
if not old:
    old = read_json(last_good_file)

raw_event = env_value("PLAYER_EVENT") or "unknown"
track_id = env_value("TRACK_ID")
old_track_id = env_value("OLD_TRACK_ID")
has_track = bool(track_id or old.get("track_id") or old.get("title"))
event = normalize_event(raw_event, old, has_track)
now = env_value("NOW")

# Build from old state first. This prevents blank librespot events from wiping metadata.
state = dict(old)
state.update({
    "schema_version": 2,
    "updated_at": now,
    "state_updated_at": now,
    "event": event,
    "raw_event": raw_event,
    "previous_event": old.get("event", ""),
    "old_track_id": old_track_id,
    "position_ms": env_or_old("POSITION_MS", old, "position_ms"),
    "duration_ms": env_or_old("DURATION_MS", old, "duration_ms"),
    "volume": env_or_old("VOLUME", old, "volume"),
    "shuffle": env_or_old("SHUFFLE", old, "shuffle"),
    "repeat": env_or_old("REPEAT", old, "repeat"),
})

if env_value("POSITION_MS") or env_value("DURATION_MS"):
    state["playback_updated_at"] = now
else:
    state["playback_updated_at"] = old.get("playback_updated_at", old.get("updated_at", now))

if track_id:
    clean_id, spotify_url = spotify_track_url(track_id)
    same_track = track_id == old.get("track_id", "")

    state["track_id"] = track_id
    state["spotify_url"] = spotify_url

    if not same_track:
        meta, error = fetch_metadata(spotify_url, clean_id)
        state["oembed_error"] = error
        if meta:
            state.update(meta)
            state["metadata_updated_at"] = now
        else:
            state["metadata_updated_at"] = old.get("metadata_updated_at", old.get("updated_at", now))
    else:
        state["title"] = old.get("title", "")
        state["author"] = old.get("author", "")
        state["thumbnail_url"] = old.get("thumbnail_url", "")
        state["local_thumbnail_url"] = old.get("local_thumbnail_url", "")
        state["provider"] = old.get("provider", "")
        state["oembed_error"] = ""
        state["metadata_updated_at"] = old.get("metadata_updated_at", old.get("updated_at", now))
else:
    # No track_id in this event. Keep last good track metadata and only update runtime status/position.
    state["track_id"] = old.get("track_id", "")
    state["spotify_url"] = old.get("spotify_url", "")
    state["title"] = old.get("title", "")
    state["author"] = old.get("author", "")
    state["thumbnail_url"] = old.get("thumbnail_url", "")
    state["local_thumbnail_url"] = old.get("local_thumbnail_url", "")
    state["provider"] = old.get("provider", "")
    state["metadata_updated_at"] = old.get("metadata_updated_at", old.get("updated_at", now))

if write_json_atomic(state_file, state):
    if state.get("track_id") and (state.get("title") or state.get("author")):
        write_json_atomic(last_good_file, state)
PY

exit 0
