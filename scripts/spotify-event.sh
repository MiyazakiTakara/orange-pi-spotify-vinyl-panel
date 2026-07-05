#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${SPOTIFY_PANEL_DIR:-/opt/spotify-panel}"
STATE_FILE="${SPOTIFY_PANEL_STATE:-$STATE_DIR/state.json}"
ENV_LOG="${SPOTIFY_PANEL_ENV_LOG:-$STATE_DIR/last-event.env}"
COVER_FILE="${SPOTIFY_PANEL_COVER:-$STATE_DIR/cover.jpg}"

mkdir -p "$STATE_DIR" 2>/dev/null || true
env | sort > "$ENV_LOG" || true
NOW="$(date -Is)"
export NOW

python3 - "$STATE_FILE" "$COVER_FILE" <<'PY'
import json
import os
import sys
import urllib.parse
import urllib.request

state_file = sys.argv[1]
cover_file = sys.argv[2]
state_dir = os.path.dirname(state_file) or "."
os.makedirs(state_dir, exist_ok=True)


def read_old():
    try:
        with open(state_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_state(data):
    tmp = state_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, state_file)


def env_or_old(name, old, key):
    value = os.environ.get(name, "")
    return value if value != "" else old.get(key, "")


def display_event(raw_event, old):
    event = (raw_event or "unknown").lower()
    # librespot emits seeked while playback continues. The UI should keep spinning.
    if event in {"seeked", "changed", "metadata", "track_changed"}:
        old_event = str(old.get("event", "playing")).lower()
        if old_event in {"paused", "stopped", "waiting"}:
            return old_event
        return "playing"
    return event


old = read_old()
raw_event = os.environ.get("PLAYER_EVENT", "unknown")
event = display_event(raw_event, old)
track_id = os.environ.get("TRACK_ID", "")
old_track_id = os.environ.get("OLD_TRACK_ID", "")

if not track_id:
    data = dict(old)
    data["updated_at"] = os.environ.get("NOW", "")
    data["event"] = event
    data["raw_event"] = raw_event
    data["position_ms"] = env_or_old("POSITION_MS", old, "position_ms")
    data["duration_ms"] = env_or_old("DURATION_MS", old, "duration_ms")
    data["volume"] = env_or_old("VOLUME", old, "volume")
    data["shuffle"] = env_or_old("SHUFFLE", old, "shuffle")
    data["repeat"] = env_or_old("REPEAT", old, "repeat")
    write_state(data)
    sys.exit(0)

clean_id = track_id.split(":")[-1] if track_id.startswith("spotify:track:") else track_id
spotify_url = "https://open.spotify.com/track/" + clean_id if clean_id else ""
same_track = track_id == old.get("track_id", "")

title = old.get("title", "") if same_track else ""
author = old.get("author", "") if same_track else ""
thumbnail_url = old.get("thumbnail_url", "") if same_track else ""
local_thumbnail_url = old.get("local_thumbnail_url", "") if same_track else ""
provider = old.get("provider", "") if same_track else ""
oembed_error = ""

if spotify_url and not same_track:
    try:
        oembed_url = "https://open.spotify.com/oembed?url=" + urllib.parse.quote(spotify_url, safe="")
        req = urllib.request.Request(oembed_url, headers={"User-Agent": "OrangePiSpotifyVinylPanel/0.1"})
        with urllib.request.urlopen(req, timeout=8) as response:
            meta = json.loads(response.read().decode("utf-8"))

        title = meta.get("title", "")
        author = meta.get("author_name", "")
        thumbnail_url = meta.get("thumbnail_url", "")
        provider = meta.get("provider_name", "")

        if thumbnail_url:
            img_req = urllib.request.Request(thumbnail_url, headers={"User-Agent": "OrangePiSpotifyVinylPanel/0.1"})
            with urllib.request.urlopen(img_req, timeout=12) as img_response:
                image_data = img_response.read()
            tmp_cover = cover_file + ".tmp"
            with open(tmp_cover, "wb") as handle:
                handle.write(image_data)
            os.replace(tmp_cover, cover_file)
            local_thumbnail_url = "/cover.jpg?track=" + clean_id
    except Exception as exc:
        oembed_error = str(exc)

state = {
    "updated_at": os.environ.get("NOW", ""),
    "event": event,
    "raw_event": raw_event,
    "track_id": track_id,
    "old_track_id": old_track_id,
    "spotify_url": spotify_url,
    "title": title,
    "author": author,
    "thumbnail_url": thumbnail_url,
    "local_thumbnail_url": local_thumbnail_url,
    "provider": provider,
    "oembed_error": oembed_error,
    "position_ms": env_or_old("POSITION_MS", old, "position_ms"),
    "duration_ms": env_or_old("DURATION_MS", old, "duration_ms"),
    "volume": env_or_old("VOLUME", old, "volume"),
    "shuffle": env_or_old("SHUFFLE", old, "shuffle"),
    "repeat": env_or_old("REPEAT", old, "repeat"),
}

write_state(state)
PY
