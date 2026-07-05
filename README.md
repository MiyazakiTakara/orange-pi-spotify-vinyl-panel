# Orange Pi Spotify Vinyl Panel

A lightweight Spotify Connect now-playing panel for Orange Pi and other small Linux audio boxes.

It is designed for a headless `librespot` receiver connected to speakers through ALSA. The web UI looks like a small turntable: spinning vinyl, moving tonearm, local cover cache, neon progress bar, track title, artist and fake knobs.

## Features

- Spotify Connect receiver integration through `librespot --onevent`
- Python standard-library web server, no Flask or Node required
- Split frontend: HTML, CSS and JavaScript are separate files
- Local JSON state endpoint: `/api/state`
- Local cover endpoint: `/cover.jpg`
- Vinyl/turntable UI with animated record and progress-driven tonearm
- Systemd service files for the panel and librespot
- Installer and uninstaller scripts
- Runtime files excluded from git

## Repository layout

```text
src/vinyl_panel/          Python web server and runtime state helpers
web/                      Frontend assets
scripts/spotify-event.sh  librespot onevent hook
systemd/                  systemd unit templates
config/                   example environment configuration
docs/                     installation and troubleshooting notes
```

## Quick install on Orange Pi

```bash
sudo apt update
sudo apt install -y python3

git clone https://github.com/MiyazakiTakara/orange-pi-spotify-vinyl-panel.git
cd orange-pi-spotify-vinyl-panel
sudo ./install.sh
```

By default the app expects:

- panel files in `/opt/spotify-panel`
- `librespot` binary at `/usr/local/bin/librespot`
- runtime user `mopidy`
- audio group `audio`
- ALSA device `plughw:0,0`
- web port `8080`

Open:

```text
http://ORANGE_PI_IP:8080
```

## Important

Spotify playback is handled by `librespot`, not by this panel. The panel only displays state and artwork received from the `librespot --onevent` hook.

## Useful commands

```bash
systemctl status spotify-panel --no-pager
systemctl status librespot --no-pager
sudo journalctl -u spotify-panel -n 100 --no-pager -l
sudo journalctl -u librespot -n 100 --no-pager -l
cat /opt/spotify-panel/state.json
cat /opt/spotify-panel/last-event.env
```

## License

MIT
