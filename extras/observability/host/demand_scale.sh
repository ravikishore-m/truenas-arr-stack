#!/usr/bin/env bash
# Demand start/stop for *arr stack. Jellyfin/telegram always left alone.
set -euo pipefail

ACTION="${1:-status}"
APPS=(sonarr radarr prowlarr qbittorrent bazarr seerr)

start_stack() {
  for app in "${APPS[@]}"; do
    midclt call app.start "$app" >/dev/null && echo "started $app" || echo "start failed $app"
  done
}

stop_stack() {
  for app in "${APPS[@]}"; do
    midclt call app.stop "$app" >/dev/null && echo "stopped $app" || echo "stop failed $app"
  done
}

status_stack() {
  midclt call app.query | python3 -c '
import json,sys
want={"sonarr","radarr","prowlarr","qbittorrent","bazarr","seerr","jellyfin","telegram-files"}
for a in json.load(sys.stdin):
  if a["name"] in want:
    print(f"{a[\"name\"]:20} {a[\"state\"]}")
'
}

case "$ACTION" in
  start) start_stack ;;
  stop) stop_stack ;;
  status) status_stack ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
