#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo: sudo ./uninstall.sh" >&2
  exit 1
fi

systemctl disable --now spotify-panel.service 2>/dev/null || true
systemctl disable --now librespot.service 2>/dev/null || true
rm -f /etc/systemd/system/spotify-panel.service
rm -f /etc/systemd/system/librespot.service
rm -f /usr/local/bin/spotify-event.sh
systemctl daemon-reload

echo "Services removed. Runtime directory /opt/spotify-panel was left in place intentionally."
