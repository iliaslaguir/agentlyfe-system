#!/usr/bin/env bash
set -euo pipefail

SERVICE="openclaw-gateway.service"

if systemctl --user is-active --quiet "$SERVICE"; then
  echo "OK: $SERVICE is running"
  exit 0
fi

echo "WARN: $SERVICE is down, restarting..."
systemctl --user restart "$SERVICE"
sleep 2

if systemctl --user is-active --quiet "$SERVICE"; then
  echo "RECOVERED: $SERVICE restarted successfully"
  exit 0
else
  echo "FAIL: $SERVICE did not restart"
  exit 1
fi
