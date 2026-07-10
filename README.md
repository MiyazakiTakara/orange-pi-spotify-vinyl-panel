# Orange Pi Spotify Vinyl Panel

A lightweight Spotify Connect now-playing panel for Orange Pi and other small Linux audio boxes.

The project combines a headless `librespot` receiver with a browser UI styled like a turntable. Playback is handled by `librespot`; the panel receives native player events, stores a normalized state, caches artwork locally and publishes realtime updates to the browser.

## Features

- Native `librespot --onevent` integration
- Fast event hook with no network requests in the playback event path
- Normalized state schema with separate current and pending tracks
- Correct handling of preload, seek, pause, resume and manual track skipping
- Realtime Server-Sent Events with automatic polling fallback
- Local per-track artwork cache under `/covers/<track-id>.jpg`
- Smooth vinyl and tonearm animation
- Responsive browser layout for desktop, tablet and phone
- Health and diagnostic endpoints
- Systemd services and an idempotent installer
- Automated regression tests and CI validation

## Architecture

```text
librespot
   │ --onevent
   ▼
spotify-event.sh
   ▼
vinyl_panel.event_hook
   │ atomic state update
   ▼
state.json
   │ shared watcher
   ▼
vinyl_panel.server
   ├── /api/events       realtime SSE
   ├── /api/state        normalized state
   ├── /api/state/raw    raw persisted state
   ├── /api/debug        diagnostics
   ├── /health           health check
   └── /covers/*.jpg     local artwork cache
```

The event hook uses metadata already supplied by current `librespot` releases, including `NAME`, `ARTISTS`, `ALBUM`, `COVERS` and `DURATION_MS`. It does not call Spotify oEmbed, so a slow network cannot block subsequent playback events.

## Repository layout

```text
src/vinyl_panel/          Python server, state model and event processor
web/                      Browser UI
scripts/spotify-event.sh  Minimal librespot hook launcher
systemd/                  systemd unit templates
config/                   Example environment configuration
tests/                    Event sequence regression tests
docs/                     Installation and troubleshooting notes
```

## Quick install on Orange Pi

```bash
sudo apt update
sudo apt install -y python3

git clone https://github.com/MiyazakiTakara/orange-pi-spotify-vinyl-panel.git
cd orange-pi-spotify-vinyl-panel
sudo ./install.sh
```

For an existing checkout:

```bash
cd /opt/orange-pi-spotify-vinyl-panel
git pull
sudo ./install.sh
```

The installer preserves an existing `/etc/default/spotify-panel`, deploys the current files and explicitly restarts both services.

## Defaults

- application directory: `/opt/spotify-panel`
- Python package directory: `/opt/spotify-panel/src`
- state file: `/opt/spotify-panel/state.json`
- artwork cache: `/opt/spotify-panel/covers`
- librespot binary: `/usr/local/bin/librespot`
- runtime user: `mopidy`
- runtime group: `audio`
- ALSA device: `plughw:0,0`
- device name: `Pomaranczowy Streamer`
- web port: `8080`

Open:

```text
http://ORANGE_PI_IP:8080
```

## Browser realtime behavior

The UI uses SSE as the primary transport. If the connection fails or becomes stale, it automatically switches to polling and reconnects in the background. The browser calculates playback progress from the locally received position using `performance.now()`, so it does not depend on clock synchronization between the viewer and Orange Pi.

Connection indicators:

- `Live` — realtime SSE is active
- `Polling` — fallback HTTP polling is active
- `Łączenie...` — reconnect is in progress
- `Brak sieci` / `Rozłączono` — the browser cannot reach the panel

## Diagnostics

```text
http://ORANGE_PI_IP:8080/health
http://ORANGE_PI_IP:8080/api/debug
http://ORANGE_PI_IP:8080/api/state
http://ORANGE_PI_IP:8080/api/state/raw
```

Useful commands:

```bash
systemctl status spotify-panel --no-pager
systemctl status librespot --no-pager
sudo journalctl -u spotify-panel -n 100 --no-pager -l
sudo journalctl -u librespot -n 100 --no-pager -l
cat /opt/spotify-panel/state.json
```

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m py_compile src/vinyl_panel/server.py src/vinyl_panel/state.py src/vinyl_panel/event_hook.py
bash -n scripts/spotify-event.sh install.sh uninstall.sh
node --check web/app.js
```

## License

MIT
