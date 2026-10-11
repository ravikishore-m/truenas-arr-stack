#!/usr/bin/env bash
# Start TrueNAS catalog apps (must already be installed via Apps UI).
set -euo pipefail
# shellcheck disable=SC1091
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"
require_key

ACTION="${1:-start}"
EXTRA_APPS=(telegram-files feishin)
ALL_APPS=("${CATALOG_APPS[@]}" "${EXTRA_APPS[@]}")

start_apps() {
  echo "Starting apps on $NAS ..."
  for app in "${ALL_APPS[@]}"; do
    printf "  %-16s " "$app"
    if nas_ssh "sudo midclt call app.start '$app'" >/dev/null 2>&1; then
      echo OK
    else
      echo "skip (not installed or already running)"
    fi
  done
}

stop_apps() {
  echo "Stopping apps on $NAS ..."
  for app in "${ALL_APPS[@]}"; do
    printf "  %-16s " "$app"
    nas_ssh "sudo midclt call app.stop '$app'" >/dev/null 2>&1 && echo OK || echo skip
  done
}

list_apps() {
  echo "Installed apps (TrueNAS):"
  nas_ssh "midclt call app.query '[[]]' | python3 -c \"
import json,sys
apps=json.load(sys.stdin)
for a in sorted(apps, key=lambda x: x.get('name','')):
    print(f\\\"  {a.get('name','?'):20} {a.get('state','?'):12}\\\")
\"" 2>/dev/null || nas_ssh "midclt call app.query" | head -c 2000
}

case "$ACTION" in
  start) start_apps ;;
  stop)  stop_apps ;;
  list)  list_apps ;;
  *) die "Usage: $0 {start|stop|list}" ;;
esac
