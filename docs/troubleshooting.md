# Troubleshooting

## Panel does not start

```bash
systemctl status spotify-panel --no-pager
sudo journalctl -u spotify-panel -n 100 --no-pager -l
```

Check Python syntax:

```bash
PYTHONPATH=/opt/spotify-panel/src python3 -m py_compile /opt/spotify-panel/src/vinyl_panel/server.py
```

## Spotify device is not visible

```bash
systemctl status librespot --no-pager
sudo journalctl -u librespot -n 100 --no-pager -l
```

Try enabling Avahi/mDNS:

```bash
sudo apt install -y avahi-daemon
sudo systemctl enable --now avahi-daemon
sudo systemctl restart librespot
```

## Music plays but UI says waiting

`librespot --onevent` sometimes sends events without `TRACK_ID`. The event script preserves the last known track in this case. Check the raw event:

```bash
cat /opt/spotify-panel/last-event.env
cat /opt/spotify-panel/state.json
```

## Cover loads slowly

The event script downloads the artwork to:

```text
/opt/spotify-panel/cover.jpg
```

Check if it exists:

```bash
ls -lh /opt/spotify-panel/cover.jpg
```

## Audio is too loud

Use ALSA mixer:

```bash
alsamixer
sudo alsactl store
```

Or change default librespot volume in:

```text
/etc/default/spotify-panel
```

Then restart:

```bash
sudo systemctl restart librespot
```
