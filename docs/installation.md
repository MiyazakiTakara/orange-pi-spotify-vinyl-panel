# Installation

## 1. Install librespot

This project does not ship `librespot`. Build or install it separately and place the binary at:

```text
/usr/local/bin/librespot
```

The systemd service expects ALSA output by default:

```text
plughw:0,0
```

Adjust `/etc/default/spotify-panel` after installation if your sound card uses another device.

## 2. Install the panel

```bash
git clone https://github.com/MiyazakiTakara/orange-pi-spotify-vinyl-panel.git
cd orange-pi-spotify-vinyl-panel
sudo ./install.sh
```

For a different runtime user:

```bash
APP_USER=patryk sudo ./install.sh
```

## 3. Open the UI

```bash
hostname -I
```

Then open:

```text
http://ORANGE_PI_IP:8080
```

## 4. Configuration

Runtime config lives in:

```text
/etc/default/spotify-panel
```

Useful values:

```text
LIBRESPOT_NAME=Orange Pi Audio
LIBRESPOT_DEVICE=plughw:0,0
LIBRESPOT_INITIAL_VOLUME=35
SPOTIFY_PANEL_PORT=8080
```

Restart after changes:

```bash
sudo systemctl daemon-reload
sudo systemctl restart spotify-panel librespot
```
