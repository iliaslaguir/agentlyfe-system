#!/usr/bin/env bash
# Restarts Dropbox if it is not running. Optional — only needed if you
# use the Dropbox A/B export feature. Override DROPBOX_DIST via env var
# if your Dropbox install lives elsewhere.
set -euo pipefail

DROPBOX_DIST="${DROPBOX_DIST:-$HOME/.dropbox-dist}"

if pgrep -f "$DROPBOX_DIST/.*/dropbox" >/dev/null 2>&1; then
  echo "OK: Dropbox is running"
  exit 0
fi

echo "WARN: Dropbox is down, starting..."
nohup "$DROPBOX_DIST/dropboxd" >/tmp/dropboxd.out 2>/tmp/dropboxd.err &
sleep 5

if pgrep -f "$DROPBOX_DIST/.*/dropbox" >/dev/null 2>&1; then
  echo "RECOVERED: Dropbox started successfully"
  exit 0
else
  echo "FAIL: Dropbox did not start"
  exit 1
fi
