#!/usr/bin/env bash
# Create config + media directory tree on the NAS.
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_key

echo "Creating directories on $NAS ..."
nas_ssh "sudo bash -s" <<REMOTE
set -euo pipefail
dirs=(
  "$CONFIG_ROOT"
  "$CONFIG_ROOT/obs-lite"
  "$CONFIG_ROOT/adguard-home/work"
  "$CONFIG_ROOT/adguard-home/conf"
  "$CONFIG_ROOT/telegram-files"
  "$CONFIG_ROOT/flac-tools"
  "$STACKS_ROOT"
  "$DOWNLOADS"
  "$MEDIA_ROOT/Movies"
  "$MEDIA_ROOT/TV"
  "$MEDIA_ROOT/Music"
  "$MEDIA_ROOT/Music/Flac"
  "$MEDIA_ROOT/.music-inbox"
)
for d in "\${dirs[@]}"; do
  mkdir -p "\$d"
  echo "  \$d"
done
# Allow apps user to own configs where helpful
chown -R ${NAS_USER}:${NAS_USER} "$CONFIG_ROOT" 2>/dev/null || true
echo "Done."
REMOTE
