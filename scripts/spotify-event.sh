#!/usr/bin/env bash
# Fast, network-free librespot event hook.
set +e

PYTHONPATH_VALUE="${SPOTIFY_PANEL_PYTHONPATH:-/opt/spotify-panel/src}"
if [[ -n "${PYTHONPATH:-}" ]]; then
  PYTHONPATH_VALUE="${PYTHONPATH_VALUE}:${PYTHONPATH}"
fi
export PYTHONPATH="$PYTHONPATH_VALUE"

exec /usr/bin/python3 -m vinyl_panel.event_hook
