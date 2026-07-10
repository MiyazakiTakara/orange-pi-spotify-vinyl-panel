#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/spotify-panel}"
APP_USER="${APP_USER:-mopidy}"
APP_GROUP="${APP_GROUP:-audio}"
PYTHON_SITE="${APP_DIR}/src"
CONFIG_FILE="/etc/default/spotify-panel"
CONFIG_EXAMPLE="/etc/default/spotify-panel.example"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./install.sh" >&2
  exit 1
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  echo "User $APP_USER does not exist. Create it or run with another APP_USER." >&2
  exit 1
fi

install -d -o "$APP_USER" -g "$APP_GROUP" -m 775 \
  "$APP_DIR" \
  "$APP_DIR/web" \
  "$PYTHON_SITE" \
  "$APP_DIR/covers" \
  /var/cache/librespot

rm -rf "$PYTHON_SITE/vinyl_panel"
cp -r src/vinyl_panel "$PYTHON_SITE/"
cp web/index.html web/styles.css web/app.js "$APP_DIR/web/"
cp scripts/spotify-event.sh /usr/local/bin/spotify-event.sh
cp systemd/spotify-panel.service /etc/systemd/system/spotify-panel.service
cp systemd/librespot.service /etc/systemd/system/librespot.service
cp config/spotify-panel.env.example "$CONFIG_EXAMPLE"

if [[ ! -f "$CONFIG_FILE" ]]; then
  cp config/spotify-panel.env.example "$CONFIG_FILE"
else
  echo "Keeping existing $CONFIG_FILE"
  echo "Fresh defaults were written to $CONFIG_EXAMPLE"
fi

chmod 755 /usr/local/bin/spotify-event.sh
chown -R "$APP_USER:$APP_GROUP" "$APP_DIR" /var/cache/librespot
chown root:root /usr/local/bin/spotify-event.sh

PYTHONPATH="$PYTHON_SITE" python3 -m py_compile \
  "$PYTHON_SITE/vinyl_panel/server.py" \
  "$PYTHON_SITE/vinyl_panel/state.py" \
  "$PYTHON_SITE/vinyl_panel/event_hook.py"

systemctl daemon-reload
systemctl enable spotify-panel.service
systemctl restart spotify-panel.service

if command -v /usr/local/bin/librespot >/dev/null 2>&1; then
  systemctl enable librespot.service
  systemctl restart librespot.service
else
  echo "WARNING: /usr/local/bin/librespot was not found. Install librespot before enabling Spotify Connect." >&2
fi

sleep 1
if ! systemctl is-active --quiet spotify-panel.service; then
  echo "ERROR: spotify-panel.service failed to start" >&2
  systemctl status spotify-panel.service --no-pager >&2 || true
  exit 1
fi

ip_addr=$(hostname -I | awk '{print $1}')
echo "Installed. Panel: http://${ip_addr}:8080"
echo "Health: http://${ip_addr}:8080/health"
echo "Debug: http://${ip_addr}:8080/api/debug"
