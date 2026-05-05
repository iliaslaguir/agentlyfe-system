#!/usr/bin/env bash
# Archives old OpenClaw session logs (>3 days) into a dated archive directory.
# Override SESSIONS_DIR / ARCHIVE_DIR via env vars if needed.
set -euo pipefail

SESSIONS_DIR="${SESSIONS_DIR:-$HOME/.openclaw/agents/main/sessions}"
ARCHIVE_DIR="${ARCHIVE_DIR:-$HOME/.openclaw/agents/main/sessions_archive/$(date +%F)}"

if [ ! -d "$SESSIONS_DIR" ]; then
  echo "Sessions dir not found: $SESSIONS_DIR"
  echo "Set SESSIONS_DIR env var to point to your OpenClaw sessions folder."
  exit 0
fi

mkdir -p "$ARCHIVE_DIR"

find "$SESSIONS_DIR" -maxdepth 1 -type f \
  \( -name "*.jsonl" -o -name "*.jsonl.deleted.*" -o -name "*.jsonl.reset.*" \) \
  -mtime +3 \
  -print0 | while IFS= read -r -d '' file; do
    base="$(basename "$file")"
    mv "$file" "$ARCHIVE_DIR/$base"
    echo "Archived: $base"
  done

echo "Done. Archive dir: $ARCHIVE_DIR"
